"""Represent one cost-basis calculation result at the application boundary."""

from dataclasses import dataclass
from typing import Any

from ...domain.cost_basis import AverageCostPoolTransition, CostBasisTransaction, OpenLotState
from .lot_state_persistence import OpenLotPersistenceScope


@dataclass(frozen=True, slots=True)
class CostBasisCalculationResult:
    """Carry calculated transactions and their required state-persistence scope."""

    processed: list[CostBasisTransaction]
    errored: list[Any]
    open_lot_states: dict[str, OpenLotState]
    incremental: bool
    open_lot_persistence_scope: OpenLotPersistenceScope
    average_cost_pool_transition: AverageCostPoolTransition | None
