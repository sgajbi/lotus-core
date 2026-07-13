"""Framework-neutral transaction-processing stage state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class TransactionStageRecord:
    """Persisted readiness state needed to publish a completed transaction stage."""

    stage_id: int
    transaction_id: str
    portfolio_id: str
    security_id: str | None
    business_date: date
    epoch: int
    status: str
    cost_event_seen: bool
