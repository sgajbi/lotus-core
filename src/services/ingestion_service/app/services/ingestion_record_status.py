from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from portfolio_common.database_models import IngestionJobFailure as DBIngestionJobFailure
from sqlalchemy import desc, select

from ..DTOs.ingestion_job_dto import IngestionJobRecordStatusResponse

SessionFactory = Callable[[], AsyncIterator[object]]

REPLAYABLE_RECORD_KEY_FIELDS: dict[str, tuple[str, str]] = {
    "/ingest/transactions": ("transactions", "transaction_id"),
    "/ingest/portfolios": ("portfolios", "portfolio_id"),
    "/ingest/instruments": ("instruments", "security_id"),
    "/ingest/business-dates": ("business_dates", "business_date"),
}


def failed_record_keys_from_failures(failures: list[Any]) -> list[str]:
    failed_keys: set[str] = set()
    for failure in failures:
        for item in list(failure.failed_record_keys or []):
            if isinstance(item, str):
                failed_keys.add(item)
    return sorted(failed_keys)


def _payload_records(payload: dict[str, Any], collection_name: str) -> list[Any]:
    records = payload.get(collection_name, [])
    return records if isinstance(records, list) else []


def _record_key_value(item: Any, key_field: str) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get(key_field)
    return str(value) if value else None


def replayable_record_keys_from_payload(
    *,
    endpoint: str,
    payload: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(payload, dict):
        return []

    record_mapping = REPLAYABLE_RECORD_KEY_FIELDS.get(endpoint)
    if record_mapping is None:
        return []

    collection_name, key_field = record_mapping
    return [
        record_key
        for item in _payload_records(payload, collection_name)
        if (record_key := _record_key_value(item, key_field)) is not None
    ]


def build_record_status_response(
    *,
    job: DBIngestionJob,
    failures: list[Any],
) -> IngestionJobRecordStatusResponse:
    payload = job.request_payload if isinstance(job.request_payload, dict) else {}
    return IngestionJobRecordStatusResponse(
        job_id=job.job_id,
        entity_type=job.entity_type,
        accepted_count=job.accepted_count,
        failed_record_keys=failed_record_keys_from_failures(failures),
        replayable_record_keys=replayable_record_keys_from_payload(
            endpoint=job.endpoint,
            payload=payload,
        ),
    )


async def load_record_status_response(
    *,
    job_id: str,
    session_factory: SessionFactory,
) -> IngestionJobRecordStatusResponse | None:
    async for db in session_factory():
        job = await db.scalar(
            select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
        )
        if job is None:
            return None
        failures = (
            await db.scalars(
                select(DBIngestionJobFailure)
                .where(DBIngestionJobFailure.job_id == job_id)
                .order_by(desc(DBIngestionJobFailure.failed_at))
            )
        ).all()
        return build_record_status_response(job=job, failures=list(failures))
    return None
