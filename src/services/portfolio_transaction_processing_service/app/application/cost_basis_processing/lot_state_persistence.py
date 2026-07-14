"""Persist calculated cost-basis lot state through application ports."""

from enum import Enum

from portfolio_common.domain.cost_basis_method import CostBasisMethod

from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
    LOT_STATE_MUTATING_BEHAVIORS,
    AverageCostPoolCheckpoint,
    AverageCostPoolTransition,
    OpenLotState,
    transaction_lot_behavior,
)
from ...domain.transaction import BookedTransaction
from ...ports import CostBasisAverageCostPoolPort, CostBasisLotStatePort


class OpenLotPersistenceScope(str, Enum):
    """Select the durable open-lot state affected by one calculation."""

    COMPLETE_SNAPSHOT = "complete_snapshot"
    SELECTED_LOTS = "selected_lots"
    AVERAGE_COST_POOL = "average_cost_pool"


async def persist_open_lot_state(
    *,
    transaction: BookedTransaction,
    effective_transaction_type: str,
    open_lot_states: dict[str, OpenLotState],
    average_cost_pools: CostBasisAverageCostPoolPort,
    lot_states: CostBasisLotStatePort,
    incremental: bool,
    persistence_scope: OpenLotPersistenceScope,
    cost_basis_method: CostBasisMethod,
    average_cost_pool_transition: AverageCostPoolTransition | None,
) -> None:
    """Persist the exact lot-state scope produced by a cost-basis calculation."""

    if average_cost_pool_transition is not None:
        await average_cost_pools.apply_average_cost_pool_transition(average_cost_pool_transition)
        return

    lot_behavior = transaction_lot_behavior(effective_transaction_type)
    mutates_lot_state = lot_behavior in LOT_STATE_MUTATING_BEHAVIORS
    incremental_opening = incremental and lot_behavior in LOT_OPENING_BEHAVIORS
    should_update_lot_states = not incremental or (mutates_lot_state and not incremental_opening)
    if should_update_lot_states:
        update_lot_states = (
            lot_states.update_selected_open_lot_states
            if persistence_scope is OpenLotPersistenceScope.SELECTED_LOTS
            else lot_states.update_open_lot_states
        )
        await update_lot_states(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            states_by_source_transaction_id=open_lot_states,
        )

    should_persist_complete_average_cost_pool = cost_basis_method is CostBasisMethod.AVCO and (
        not incremental or (mutates_lot_state and not incremental_opening)
    )
    if should_persist_complete_average_cost_pool:
        await average_cost_pools.upsert_average_cost_pool_checkpoint(
            AverageCostPoolCheckpoint.from_open_lot_states(
                portfolio_id=transaction.portfolio_id,
                instrument_id=transaction.instrument_id,
                security_id=transaction.security_id,
                states_by_source_transaction_id=open_lot_states,
            )
        )
