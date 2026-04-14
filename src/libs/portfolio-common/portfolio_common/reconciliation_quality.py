"""RFC-0083 reconciliation and data-quality status helpers."""

from __future__ import annotations

from dataclasses import dataclass


COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
STALE = "STALE"
UNRECONCILED = "UNRECONCILED"
BREAK_OPEN = "BREAK_OPEN"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"

BLOCKING_RUN_STATUSES = {"FAILED", "REQUIRES_REPLAY", "BLOCKED"}
COMPLETE_RUN_STATUSES = {"COMPLETED", "COMPLETE"}
RUNNING_RUN_STATUSES = {"RUNNING", "PROCESSING", "ACCEPTED", "QUEUED", "PENDING"}

BLOCKING_FINDING_SEVERITIES = {"ERROR", "CRITICAL", "BLOCKER"}
NON_BLOCKING_FINDING_SEVERITIES = {"WARNING", "INFO"}


@dataclass(frozen=True)
class ReconciliationRunSignal:
    run_status: str | None
    error_count: int = 0
    warning_count: int = 0
    is_stale: bool = False
    has_run: bool = True


@dataclass(frozen=True)
class ReconciliationBreakSignal:
    finding_id: str
    severity: str
    is_blocking: bool
    age_days: int
    resolution_state: str = "OPEN"
    owner: str | None = None


@dataclass(frozen=True)
class DataQualityCoverageSignal:
    required_count: int
    observed_count: int
    stale_count: int = 0
    blocking_issue_count: int = 0
    warning_issue_count: int = 0


def classify_reconciliation_status(signal: ReconciliationRunSignal) -> str:
    _require_non_negative(signal.error_count, "error_count")
    _require_non_negative(signal.warning_count, "warning_count")
    if not signal.has_run:
        return UNRECONCILED
    if signal.is_stale:
        return STALE
    status = _normalize_status(signal.run_status)
    if status is None:
        return UNKNOWN
    if status in BLOCKING_RUN_STATUSES or signal.error_count > 0:
        return BLOCKED
    if signal.warning_count > 0:
        return PARTIAL
    if status in COMPLETE_RUN_STATUSES:
        return COMPLETE
    if status in RUNNING_RUN_STATUSES:
        return PARTIAL
    return UNKNOWN


def classify_finding_status(*, severity: str, resolution_state: str = "OPEN") -> str:
    normalized_resolution = _normalize_required_text(resolution_state, "resolution_state")
    if normalized_resolution in {"RESOLVED", "WAIVED", "SUPPRESSED"}:
        return COMPLETE
    normalized_severity = _normalize_required_text(severity, "severity")
    if normalized_severity in BLOCKING_FINDING_SEVERITIES:
        return BLOCKED
    if normalized_severity in NON_BLOCKING_FINDING_SEVERITIES:
        return BREAK_OPEN
    return UNKNOWN


def classify_data_quality_coverage(signal: DataQualityCoverageSignal) -> str:
    _require_non_negative(signal.required_count, "required_count")
    _require_non_negative(signal.observed_count, "observed_count")
    _require_non_negative(signal.stale_count, "stale_count")
    _require_non_negative(signal.blocking_issue_count, "blocking_issue_count")
    _require_non_negative(signal.warning_issue_count, "warning_issue_count")
    if signal.blocking_issue_count > 0:
        return BLOCKED
    if signal.required_count == 0:
        return UNKNOWN
    if signal.observed_count == 0:
        return UNRECONCILED
    if signal.stale_count > 0:
        return STALE
    if signal.observed_count < signal.required_count or signal.warning_issue_count > 0:
        return PARTIAL
    return COMPLETE


def sort_reconciliation_breaks(
    breaks: list[ReconciliationBreakSignal],
) -> list[ReconciliationBreakSignal]:
    return sorted(
        breaks,
        key=lambda item: (
            0 if item.is_blocking else 1,
            _severity_rank(item.severity),
            -item.age_days,
            item.finding_id,
        ),
    )


def _severity_rank(severity: str) -> int:
    normalized = _normalize_required_text(severity, "severity")
    return {
        "BLOCKER": 0,
        "CRITICAL": 1,
        "ERROR": 2,
        "WARNING": 3,
        "INFO": 4,
    }.get(normalized, 9)


def _normalize_status(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().upper() or None


def _normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
