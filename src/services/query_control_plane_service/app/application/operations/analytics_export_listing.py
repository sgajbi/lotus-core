"""Build tenant-scoped analytics export support responses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, Sequence

from ...contracts.operations import AnalyticsExportJobListResponse, AnalyticsExportJobRecord
from .runtime_state import (
    analytics_export_operational_state,
    is_analytics_export_job_stale,
    normalize_analytics_export_status,
)


class AnalyticsExportSupportRow(Protocol):
    job_id: str
    request_fingerprint: str
    dataset_type: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime | None
    result_row_count: int | None
    error_message: str | None


def build_analytics_export_job_list_response(
    *,
    portfolio_id: str,
    stale_threshold_minutes: int,
    generated_at_utc: datetime,
    total: int,
    skip: int,
    limit: int,
    jobs: Sequence[AnalyticsExportSupportRow],
) -> AnalyticsExportJobListResponse:
    return AnalyticsExportJobListResponse(
        portfolio_id=portfolio_id,
        stale_threshold_minutes=stale_threshold_minutes,
        generated_at_utc=generated_at_utc,
        total=total,
        skip=skip,
        limit=limit,
        items=[
            AnalyticsExportJobRecord(
                job_id=job.job_id,
                request_fingerprint=job.request_fingerprint,
                dataset_type=job.dataset_type,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                updated_at=job.updated_at,
                is_stale_running=is_analytics_export_job_stale(
                    job.status,
                    job.updated_at,
                    generated_at_utc,
                    stale_threshold_minutes,
                ),
                backlog_age_minutes=analytics_export_backlog_age_minutes(
                    job.status, job.created_at, generated_at_utc
                ),
                result_row_count=job.result_row_count,
                error_message=job.error_message,
                is_terminal_failure=normalize_analytics_export_status(job.status) == "failed",
                operational_state=analytics_export_operational_state(
                    job.status,
                    job.updated_at,
                    generated_at_utc,
                    stale_threshold_minutes,
                ),
            )
            for job in jobs
        ],
    )


def analytics_export_backlog_age_minutes(
    status: str | None,
    created_at: datetime | None,
    now: datetime | None = None,
) -> int | None:
    normalized_status = normalize_analytics_export_status(status)
    if normalized_status not in {"accepted", "running"} or created_at is None:
        return None
    reference_now = now or datetime.now(timezone.utc)
    return max(0, int((reference_now - created_at).total_seconds() // 60))
