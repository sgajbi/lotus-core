from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ..dtos.operations_dto import SupportJobRecord
from ..repositories.identifier_normalization import normalize_security_id
from ..support_policy import DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES


def normalize_support_job_status(status: str | None) -> str | None:
    if status is None:
        return None
    return status.strip().upper()


def is_support_job_stale(
    status: str | None,
    updated_at: datetime | None,
    now: datetime | None = None,
    stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
) -> bool:
    if normalize_support_job_status(status) != "PROCESSING" or updated_at is None:
        return False
    reference_now = now or datetime.now(timezone.utc)
    return updated_at < reference_now - timedelta(minutes=stale_threshold_minutes)


def is_terminal_failure_status(status: str | None) -> bool:
    return normalize_support_job_status(status) == "FAILED"


def is_support_job_retrying(status: str, attempt_count: int | None) -> bool:
    normalized_status = normalize_support_job_status(status)
    return (attempt_count or 0) > 0 and normalized_status in {"PENDING", "PROCESSING"}


def get_support_job_operational_state(
    status: str,
    updated_at: datetime | None,
    now: datetime | None = None,
    stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
) -> str:
    normalized_status = normalize_support_job_status(status) or ""
    if normalized_status == "FAILED":
        return "FAILED"
    if normalized_status.startswith("SKIPPED"):
        return "SKIPPED"
    if is_support_job_stale(normalized_status, updated_at, now, stale_threshold_minutes):
        return "STALE_PROCESSING"
    if normalized_status == "PROCESSING":
        return "PROCESSING"
    if normalized_status == "PENDING":
        return "PENDING"
    return "COMPLETED"


def build_support_job_record(
    *,
    job_id: int,
    job_type: str,
    business_date: date,
    status: str,
    security_id: str | None,
    epoch: int | None,
    attempt_count: int | None,
    correlation_id: str | None,
    created_at: datetime | None,
    updated_at: datetime | None,
    failure_reason: str | None,
    reference_now: datetime | None = None,
    stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
) -> SupportJobRecord:
    return SupportJobRecord(
        job_id=job_id,
        job_type=job_type,
        business_date=business_date,
        status=status,
        security_id=normalize_security_id(security_id) if security_id is not None else None,
        epoch=epoch,
        attempt_count=attempt_count,
        is_retrying=is_support_job_retrying(status, attempt_count),
        correlation_id=correlation_id,
        created_at=created_at,
        updated_at=updated_at,
        is_stale_processing=is_support_job_stale(
            status,
            updated_at,
            reference_now,
            stale_threshold_minutes,
        ),
        failure_reason=failure_reason,
        is_terminal_failure=is_terminal_failure_status(status),
        operational_state=get_support_job_operational_state(
            status,
            updated_at,
            reference_now,
            stale_threshold_minutes,
        ),
    )
