from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

TRANSACTION_PROCESSING_STAGE = "TRANSACTION_PROCESSING"
FINANCIAL_RECONCILIATION_STAGE = "FINANCIAL_RECONCILIATION"
CONTROL_BLOCKING_STATUSES = frozenset({"FAILED", "REQUIRES_REPLAY"})


class TransactionStageState(Protocol):
    status: str
    cost_event_seen: bool
    cashflow_event_seen: bool


@dataclass(frozen=True)
class TransactionStageReadinessDecision:
    should_complete: bool
    reason_code: str


def decide_transaction_stage_readiness(
    stage: TransactionStageState,
) -> TransactionStageReadinessDecision:
    if stage.status == "COMPLETED":
        return TransactionStageReadinessDecision(
            should_complete=False,
            reason_code="already_completed",
        )
    if not stage.cost_event_seen:
        return TransactionStageReadinessDecision(
            should_complete=False,
            reason_code="missing_cost_event",
        )
    if not stage.cashflow_event_seen:
        return TransactionStageReadinessDecision(
            should_complete=False,
            reason_code="missing_cashflow_event",
        )
    return TransactionStageReadinessDecision(
        should_complete=True,
        reason_code="ready",
    )


def is_control_stage_blocking(status: str) -> bool:
    return status in CONTROL_BLOCKING_STATUSES


def should_emit_control_stage_for_epoch(
    *,
    latest_epoch: int | None,
    event_epoch: int,
) -> bool:
    return latest_epoch is None or latest_epoch == event_epoch
