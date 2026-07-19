"""Domain records and policies for financial reconciliation control evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

CONTROL_BLOCKING_STATUSES = frozenset({"FAILED", "REQUIRES_REPLAY"})


@dataclass(frozen=True, slots=True)
class FinancialReconciliationCompletion:
    """Outcome of one automatic reconciliation bundle for a portfolio day."""

    portfolio_id: str
    business_date: date
    epoch: int
    aggregation_revision: int
    outcome_status: str
    reconciliation_types: tuple[str, ...]
    blocking_reconciliation_types: tuple[str, ...]
    run_ids: Mapping[str, str]
    error_count: int
    warning_count: int
    requested_by: str
    trigger_stage: str

    def __post_init__(self) -> None:
        if self.aggregation_revision < 0:
            raise ValueError("Financial reconciliation aggregation revision cannot be negative.")


@dataclass(frozen=True, slots=True)
class RecordedReconciliationControl:
    """Persisted control status and the latest known portfolio-day epoch."""

    status: str
    latest_epoch: int | None
    accepted_revision: bool


def is_control_blocking(status: str) -> bool:
    """Return whether a control outcome must block downstream publication."""

    return status in CONTROL_BLOCKING_STATUSES


def should_emit_controls_for_epoch(
    *,
    latest_epoch: int | None,
    completed_epoch: int,
) -> bool:
    """Suppress stale control outcomes when a later portfolio-day epoch exists."""

    return latest_epoch is None or latest_epoch == completed_epoch
