"""Atomic persistence boundary for one initial cost-basis opening state."""

from typing import Protocol

from ...domain.cost_basis import CostBasisProcessingCheckpoint, CostBasisTransaction


class InitialOpeningCostStatePort(Protocol):
    """Persist the state first established by an ordinary opening purchase."""

    async def persist_initial_opening_cost_state(
        self,
        *,
        transaction: CostBasisTransaction,
        checkpoint: CostBasisProcessingCheckpoint,
    ) -> None: ...
