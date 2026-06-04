from __future__ import annotations

from datetime import date, datetime

from portfolio_common.reconciliation_quality import BLOCKED, BREAK_OPEN, COMPLETE, PARTIAL, UNKNOWN

from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..support_policy import DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES
from .support_job_record_builder import is_support_job_stale

_ANALYTICS_EXPORT_TERMINAL_STATES = {
    "failed": "FAILED",
    "running": "RUNNING",
    "accepted": "ACCEPTED",
}


def evidence_product_runtime_metadata(
    *,
    generated_at_utc: datetime,
    as_of_dates: list[date | None],
    evidence_timestamps: list[datetime | None],
    reconciliation_status: str = UNKNOWN,
) -> dict[str, object]:
    return source_data_product_runtime_metadata(
        as_of_date=_latest_as_of_date(as_of_dates, generated_at_utc),
        generated_at=generated_at_utc,
        reconciliation_status=reconciliation_status,
        latest_evidence_timestamp=_latest_evidence_timestamp(evidence_timestamps),
    )


def aggregate_reconciliation_statuses(statuses: list[str]) -> str:
    if not statuses:
        return UNKNOWN
    status_rank = {
        BLOCKED: 4,
        BREAK_OPEN: 3,
        PARTIAL: 2,
        COMPLETE: 1,
    }
    strongest_status = max(statuses, key=lambda status: status_rank.get(status, 0))
    if strongest_status in {BLOCKED, BREAK_OPEN, PARTIAL}:
        return strongest_status
    if all(status == COMPLETE for status in statuses):
        return COMPLETE
    return UNKNOWN


def normalize_analytics_export_status(status: str | None) -> str | None:
    if status is None:
        return None
    return status.strip().lower()


def normalize_analytics_export_status_filter(status: str | None) -> str | None:
    normalized_status = normalize_analytics_export_status(status)
    return normalized_status or None


def analytics_export_operational_state(
    status: str,
    updated_at: datetime | None,
    now: datetime | None = None,
    stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
) -> str:
    normalized_status = normalize_analytics_export_status(status) or ""
    if _is_running_export_stale(
        normalized_status,
        updated_at,
        now,
        stale_threshold_minutes,
    ):
        return "STALE_RUNNING"
    return _ANALYTICS_EXPORT_TERMINAL_STATES.get(normalized_status, "COMPLETED")


def is_analytics_export_job_stale(
    status: str | None,
    updated_at: datetime | None,
    now: datetime | None = None,
    stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
) -> bool:
    normalized_status = normalize_analytics_export_status(status)
    support_status = "PROCESSING" if normalized_status == "running" else normalized_status
    return is_support_job_stale(
        support_status,
        updated_at,
        now,
        stale_threshold_minutes,
    )


def _latest_as_of_date(as_of_dates: list[date | None], generated_at_utc: datetime) -> date:
    resolved_as_of_dates = [as_of_date for as_of_date in as_of_dates if as_of_date is not None]
    return max(resolved_as_of_dates, default=generated_at_utc.date())


def _latest_evidence_timestamp(evidence_timestamps: list[datetime | None]) -> datetime | None:
    resolved_timestamps = [
        evidence_timestamp
        for evidence_timestamp in evidence_timestamps
        if evidence_timestamp is not None
    ]
    return max(resolved_timestamps, default=None)


def _is_running_export_stale(
    normalized_status: str,
    updated_at: datetime | None,
    now: datetime | None,
    stale_threshold_minutes: int,
) -> bool:
    return normalized_status == "running" and is_analytics_export_job_stale(
        normalized_status,
        updated_at,
        now,
        stale_threshold_minutes,
    )
