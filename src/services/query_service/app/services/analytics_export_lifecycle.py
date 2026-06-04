from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .analytics_export_jobs import normalize_analytics_export_job_status


def export_job_is_completed(row: object) -> bool:
    return normalize_analytics_export_job_status(row.status) == "completed"


def export_job_is_inflight(row: object) -> bool:
    return normalize_analytics_export_job_status(row.status) in {"accepted", "running"}


def export_job_stale_threshold(
    *,
    timeout_minutes: int,
    reference_now: datetime | None = None,
) -> datetime:
    reference_time = reference_now or datetime.now(UTC)
    return reference_time - timedelta(minutes=timeout_minutes)


def export_job_is_fresh(
    row: object,
    *,
    timeout_minutes: int,
    reference_now: datetime | None = None,
) -> bool:
    return row.updated_at is not None and row.updated_at >= export_job_stale_threshold(
        timeout_minutes=timeout_minutes,
        reference_now=reference_now,
    )
