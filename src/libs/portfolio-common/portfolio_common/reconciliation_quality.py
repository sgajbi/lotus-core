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
_RUN_STATUS_CLASSIFICATION_BY_STATUS = {
    **dict.fromkeys(COMPLETE_RUN_STATUSES, COMPLETE),
    **dict.fromkeys(RUNNING_RUN_STATUSES, PARTIAL),
}

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
    _validate_reconciliation_run_signal(signal)
    if not signal.has_run:
        return UNRECONCILED
    return _classify_reconciliation_run_status(
        status=_normalize_status(signal.run_status),
        error_count=signal.error_count,
        warning_count=signal.warning_count,
        is_stale=signal.is_stale,
    )


def _validate_reconciliation_run_signal(signal: ReconciliationRunSignal) -> None:
    _require_non_negative(signal.error_count, "error_count")
    _require_non_negative(signal.warning_count, "warning_count")


def _classify_reconciliation_run_status(
    *,
    status: str | None,
    error_count: int,
    warning_count: int,
    is_stale: bool,
) -> str:
    if status is None:
        return UNKNOWN
    if _has_blocking_run_status(status=status, error_count=error_count):
        return BLOCKED
    if is_stale:
        return STALE
    if warning_count > 0:
        return PARTIAL
    return _RUN_STATUS_CLASSIFICATION_BY_STATUS.get(status, UNKNOWN)


def _has_blocking_run_status(*, status: str, error_count: int) -> bool:
    return status in BLOCKING_RUN_STATUSES or error_count > 0


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
    _validate_data_quality_coverage_signal(signal)
    return _classify_data_quality_coverage_counts(
        required_count=signal.required_count,
        observed_count=signal.observed_count,
        stale_count=signal.stale_count,
        blocking_issue_count=signal.blocking_issue_count,
        warning_issue_count=signal.warning_issue_count,
    )


def _validate_data_quality_coverage_signal(signal: DataQualityCoverageSignal) -> None:
    _require_non_negative(signal.required_count, "required_count")
    _require_non_negative(signal.observed_count, "observed_count")
    _require_non_negative(signal.stale_count, "stale_count")
    _require_non_negative(signal.blocking_issue_count, "blocking_issue_count")
    _require_non_negative(signal.warning_issue_count, "warning_issue_count")


def _classify_data_quality_coverage_counts(
    *,
    required_count: int,
    observed_count: int,
    stale_count: int,
    blocking_issue_count: int,
    warning_issue_count: int,
) -> str:
    if blocking_issue_count > 0:
        return BLOCKED
    return _classify_nonblocking_data_quality_coverage(
        required_count=required_count,
        observed_count=observed_count,
        stale_count=stale_count,
        warning_issue_count=warning_issue_count,
    )


def _classify_nonblocking_data_quality_coverage(
    *,
    required_count: int,
    observed_count: int,
    stale_count: int,
    warning_issue_count: int,
) -> str:
    if required_count == 0:
        return UNKNOWN
    if observed_count == 0:
        return UNRECONCILED
    if stale_count > 0:
        return STALE
    if _has_partial_data_quality_coverage(
        required_count=required_count,
        observed_count=observed_count,
        warning_issue_count=warning_issue_count,
    ):
        return PARTIAL
    return COMPLETE


def _has_partial_data_quality_coverage(
    *,
    required_count: int,
    observed_count: int,
    warning_issue_count: int,
) -> bool:
    return observed_count < required_count or warning_issue_count > 0


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
