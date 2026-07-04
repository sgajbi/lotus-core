from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ReconciliationRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    REQUIRES_REPLAY = "REQUIRES_REPLAY"
    FAILED = "FAILED"

    @classmethod
    def normalize(cls, value: object) -> "ReconciliationRunStatus | None":
        if not isinstance(value, str):
            return None
        normalized = value.strip().upper()
        for status in cls:
            if status.value == normalized:
                return status
        return None


@dataclass(frozen=True, slots=True)
class ReconciliationRunTransition:
    name: str
    source_statuses: frozenset[ReconciliationRunStatus]
    target_status: ReconciliationRunStatus
    requires_summary: bool
    requires_findings_persisted: bool


@dataclass(frozen=True, slots=True)
class ReconciliationRunLifecycleSnapshot:
    run_id: str
    status: ReconciliationRunStatus | None
    error_count: int
    warning_count: int


@dataclass(frozen=True, slots=True)
class AutomaticBundleOutcome:
    outcome_status: str
    blocking_reconciliation_types: list[str]
    run_ids: dict[str, str]
    error_count: int
    warning_count: int


COMPLETE_RECONCILIATION_RUN = ReconciliationRunTransition(
    name="complete_reconciliation_run",
    source_statuses=frozenset({ReconciliationRunStatus.RUNNING}),
    target_status=ReconciliationRunStatus.COMPLETED,
    requires_summary=True,
    requires_findings_persisted=True,
)

TERMINAL_RECONCILIATION_RUN_STATUSES = frozenset(
    {
        ReconciliationRunStatus.COMPLETED,
        ReconciliationRunStatus.REQUIRES_REPLAY,
        ReconciliationRunStatus.FAILED,
    }
)
RETRYABLE_RECONCILIATION_RUN_STATUSES = frozenset(
    {
        ReconciliationRunStatus.REQUIRES_REPLAY,
        ReconciliationRunStatus.FAILED,
    }
)


def initial_reconciliation_run_status() -> str:
    return ReconciliationRunStatus.RUNNING.value


def completed_reconciliation_run_status() -> str:
    return COMPLETE_RECONCILIATION_RUN.target_status.value


def is_terminal_reconciliation_run_status(status: object) -> bool:
    normalized = ReconciliationRunStatus.normalize(status)
    return normalized in TERMINAL_RECONCILIATION_RUN_STATUSES


def is_retryable_reconciliation_run_status(status: object) -> bool:
    normalized = ReconciliationRunStatus.normalize(status)
    return normalized in RETRYABLE_RECONCILIATION_RUN_STATUSES


def determine_automatic_bundle_outcome(
    runs: Mapping[str, ReconciliationRunLifecycleSnapshot],
) -> AutomaticBundleOutcome:
    blocking_types: list[str] = []
    run_ids: dict[str, str] = {}
    error_count = 0
    warning_count = 0
    has_failed_run = False

    for reconciliation_type, run in runs.items():
        run_ids[reconciliation_type] = run.run_id
        error_count += run.error_count
        warning_count += run.warning_count

        if run.status is ReconciliationRunStatus.FAILED:
            has_failed_run = True
            blocking_types.append(reconciliation_type)
            continue
        if run.error_count > 0:
            blocking_types.append(reconciliation_type)

    if has_failed_run:
        outcome_status = ReconciliationRunStatus.FAILED.value
    elif blocking_types:
        outcome_status = ReconciliationRunStatus.REQUIRES_REPLAY.value
    else:
        outcome_status = ReconciliationRunStatus.COMPLETED.value

    return AutomaticBundleOutcome(
        outcome_status=outcome_status,
        blocking_reconciliation_types=sorted(set(blocking_types)),
        run_ids=run_ids,
        error_count=error_count,
        warning_count=warning_count,
    )
