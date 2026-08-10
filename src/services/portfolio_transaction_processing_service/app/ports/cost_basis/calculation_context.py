"""Typed read model for one cost-basis calculation frontier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...domain.cost_basis import CostBasisProcessingCheckpoint
from ...domain.transaction import BookedTransaction


@dataclass(frozen=True, slots=True)
class CostBasisCalculationContext:
    """Carry the durable checkpoint and conditionally loaded initial history."""

    checkpoint: CostBasisProcessingCheckpoint | None
    transaction_history: tuple[BookedTransaction, ...] | None


class CostBasisCalculationContextPort(Protocol):
    """Load one post-lock calculation frontier from a single database snapshot."""

    async def load_cost_basis_calculation_context(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        exclude_transaction_id: str,
        include_initial_history: bool,
    ) -> CostBasisCalculationContext: ...
