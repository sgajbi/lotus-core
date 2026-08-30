"""Analytics export job lifecycle and staleness policies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ...contracts.analytics_inputs import AnalyticsExportCreateRequest
from ...domain.analytics import AnalyticsExportJobRecord
from ...ports.analytics import AnalyticsExportStore, AnalyticsUnitOfWork
from .analytics_errors import AnalyticsInputError
from .analytics_export_jobs import normalize_analytics_export_job_status


def export_job_is_completed(row: AnalyticsExportJobRecord) -> bool:
    return normalize_analytics_export_job_status(row.status) == "completed"


def export_job_is_inflight(row: AnalyticsExportJobRecord) -> bool:
    return normalize_analytics_export_job_status(row.status) in {"accepted", "running"}


def export_job_stale_threshold(
    *,
    timeout_minutes: int,
    reference_now: datetime | None = None,
) -> datetime:
    reference_time = reference_now or datetime.now(UTC)
    return reference_time - timedelta(minutes=timeout_minutes)


def export_job_is_fresh(
    row: AnalyticsExportJobRecord,
    *,
    timeout_minutes: int,
    reference_now: datetime | None = None,
) -> bool:
    return row.updated_at is not None and row.updated_at >= export_job_stale_threshold(
        timeout_minutes=timeout_minutes,
        reference_now=reference_now,
    )


async def reserve_tenant_export_job(
    *,
    store: AnalyticsExportStore,
    unit_of_work: AnalyticsUnitOfWork,
    tenant_id: str,
    request: AnalyticsExportCreateRequest,
    request_payload: dict[str, object],
    request_fingerprint: str,
    stale_timeout_minutes: int,
) -> tuple[AnalyticsExportJobRecord, bool]:
    """Reuse or create one export job inside its immutable tenant scope."""

    async with unit_of_work.transaction():
        existing = await store.get_latest_by_fingerprint(
            tenant_id=tenant_id,
            request_fingerprint=request_fingerprint,
            dataset_type=request.dataset_type,
        )
        if existing is not None:
            if export_job_is_completed(existing):
                return existing, True
            if export_job_is_inflight(existing):
                if export_job_is_fresh(
                    existing,
                    timeout_minutes=stale_timeout_minutes,
                ):
                    return existing, True
                await store.mark_failed(
                    existing,
                    tenant_id=tenant_id,
                    error_message="Stale analytics export job superseded by a new request.",
                )

        row = await store.create_job(
            job_id=f"aexp_{uuid4().hex[:24]}",
            tenant_id=tenant_id,
            dataset_type=request.dataset_type,
            portfolio_id=request.portfolio_id,
            request_fingerprint=request_fingerprint,
            request_payload=request_payload,
            result_format=request.result_format,
            compression=request.compression,
        )
        return row, False


async def mark_tenant_export_job_running(
    *,
    store: AnalyticsExportStore,
    unit_of_work: AnalyticsUnitOfWork,
    tenant_id: str,
    job_id: str,
) -> AnalyticsExportJobRecord:
    async with unit_of_work.transaction():
        row = await _require_tenant_export_job(store, tenant_id=tenant_id, job_id=job_id)
        return await store.mark_running(row, tenant_id=tenant_id)


async def mark_tenant_export_job_completed(
    *,
    store: AnalyticsExportStore,
    unit_of_work: AnalyticsUnitOfWork,
    tenant_id: str,
    job_id: str,
    result_payload: dict[str, object],
    result_row_count: int,
) -> AnalyticsExportJobRecord:
    async with unit_of_work.transaction():
        row = await _require_tenant_export_job(store, tenant_id=tenant_id, job_id=job_id)
        return await store.mark_completed(
            row,
            tenant_id=tenant_id,
            result_payload=result_payload,
            result_row_count=result_row_count,
        )


async def mark_tenant_export_job_failed(
    *,
    store: AnalyticsExportStore,
    unit_of_work: AnalyticsUnitOfWork,
    tenant_id: str,
    job_id: str,
    error_message: str,
) -> AnalyticsExportJobRecord:
    async with unit_of_work.transaction():
        row = await _require_tenant_export_job(store, tenant_id=tenant_id, job_id=job_id)
        return await store.mark_failed(
            row,
            tenant_id=tenant_id,
            error_message=error_message,
        )


async def _require_tenant_export_job(
    store: AnalyticsExportStore,
    *,
    tenant_id: str,
    job_id: str,
) -> AnalyticsExportJobRecord:
    row = await store.get_job(tenant_id=tenant_id, job_id=job_id)
    if row is None:
        raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
    return row
