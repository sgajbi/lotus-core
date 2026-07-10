from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


@dataclass(frozen=True, order=True, slots=True)
class AverageCostPoolKey:
    portfolio_id: str
    security_id: str

    def __post_init__(self) -> None:
        if not self.portfolio_id.strip() or not self.security_id.strip():
            raise ValueError("Average cost pool key identifiers must not be blank")


class AverageCostPoolReconciliationStatus(StrEnum):
    CURRENT = "current"
    DRIFTED = "drifted"
    RECONCILED = "reconciled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AverageCostPoolReconciliationAssessment:
    key: AverageCostPoolKey
    status: AverageCostPoolReconciliationStatus
    source_count: int
    pool_quantity: Decimal | None
    pool_cost_local: Decimal | None
    pool_cost_base: Decimal | None
    source_quantity: Decimal
    source_cost_local: Decimal
    source_cost_base: Decimal
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.source_count < 0:
            raise ValueError("Average cost source count must be nonnegative")
        amounts = (
            self.pool_quantity,
            self.pool_cost_local,
            self.pool_cost_base,
            self.source_quantity,
            self.source_cost_local,
            self.source_cost_base,
        )
        if any(amount is not None and amount < Decimal(0) for amount in amounts):
            raise ValueError("Average cost reconciliation amounts must be nonnegative")

        reason_code = self.reason_code.strip() if self.reason_code else None
        object.__setattr__(self, "reason_code", reason_code)
        is_exact = self._pool_matches_sources()
        if self.status in {
            AverageCostPoolReconciliationStatus.CURRENT,
            AverageCostPoolReconciliationStatus.RECONCILED,
        }:
            if not is_exact:
                raise ValueError("Current average cost state must reconcile exactly")
            if reason_code is not None:
                raise ValueError("Current average cost state must not carry a failure reason")
        elif reason_code is None:
            raise ValueError("Drifted or failed average cost state requires a reason code")

    def _pool_matches_sources(self) -> bool:
        return (
            self.pool_quantity is not None
            and self.pool_cost_local is not None
            and self.pool_cost_base is not None
            and self.pool_quantity == self.source_quantity
            and self.pool_cost_local == self.source_cost_local
            and self.pool_cost_base == self.source_cost_base
        )
