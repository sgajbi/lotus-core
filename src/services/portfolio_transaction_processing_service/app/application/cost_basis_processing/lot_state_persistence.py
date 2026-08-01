"""Persist calculated cost-basis lot state through application ports."""

from collections.abc import Sequence
from enum import Enum

from portfolio_common.domain.calculation_lineage import CalculationLineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
    LOT_STATE_MUTATING_BEHAVIORS,
    AverageCostPoolCheckpoint,
    AverageCostPoolTransition,
    CostBasisTransaction,
    OpenLotState,
    transaction_lot_behavior,
)
from ...domain.cost_basis.state_lineage import (
    CostBasisStateTransitionEvidence,
    build_cost_basis_state_lineage,
)
from ...domain.transaction import BookedTransaction
from ...ports import CostBasisAverageCostPoolPort, CostBasisLotStatePort


class OpenLotPersistenceScope(str, Enum):
    """Select the durable open-lot state affected by one calculation."""

    COMPLETE_SNAPSHOT = "complete_snapshot"
    INITIAL_OPENING_LOT = "initial_opening_lot"
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
    processed: Sequence[CostBasisTransaction],
) -> None:
    """Persist the exact lot-state scope produced by a cost-basis calculation."""

    if average_cost_pool_transition is not None:
        await average_cost_pools.apply_average_cost_pool_transition(average_cost_pool_transition)
        return

    lot_behavior = transaction_lot_behavior(effective_transaction_type)
    mutates_lot_state = lot_behavior in LOT_STATE_MUTATING_BEHAVIORS
    incremental_opening = incremental and lot_behavior in LOT_OPENING_BEHAVIORS
    initial_opening_lot = persistence_scope is OpenLotPersistenceScope.INITIAL_OPENING_LOT
    should_update_lot_states = not initial_opening_lot and (
        not incremental or (mutates_lot_state and not incremental_opening)
    )
    if should_update_lot_states:
        transition_evidence = _transition_evidence(
            transaction=transaction,
            processed=processed,
            transition_kind=persistence_scope.value,
            open_lot_states=open_lot_states,
        )
        update_lot_states = (
            lot_states.update_selected_open_lot_states
            if persistence_scope is OpenLotPersistenceScope.SELECTED_LOTS
            else lot_states.update_open_lot_states
        )
        await update_lot_states(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            states_by_source_transaction_id=open_lot_states,
            transition_evidence=transition_evidence,
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


def _transition_evidence(
    *,
    transaction: BookedTransaction,
    processed: Sequence[CostBasisTransaction],
    transition_kind: str,
    open_lot_states: dict[str, OpenLotState],
) -> CostBasisStateTransitionEvidence:
    calculated_transactions: list[dict[str, object]] = []
    for item in processed:
        lineage = getattr(item, "calculation_lineage", None)
        if not isinstance(lineage, CalculationLineage):
            raise ValueError(f"Calculated transaction lacks lineage: {item.transaction_id}")
        calculated_transactions.append(
            {
                "calculation_lineage": lineage.lineage_payload(),
                "transaction_id": item.transaction_id,
            }
        )
    trigger_lineage = transaction.calculation_lineage
    trigger_payload = {
        "calculation_lineage": (
            trigger_lineage.lineage_payload() if trigger_lineage is not None else None
        ),
        "component_type": transaction.component_type,
        "originating_transaction_id": transaction.originating_transaction_id,
        "gross_transaction_amount": transaction.gross_transaction_amount,
        "portfolio_id": transaction.portfolio_id,
        "child_sequence_hint": transaction.child_sequence_hint,
        "quantity": transaction.quantity,
        "security_id": transaction.security_id,
        "transaction_date": transaction.transaction_date.isoformat(),
        "transaction_id": transaction.transaction_id,
        "transaction_type": transaction.transaction_type,
    }
    transition_lineage = build_cost_basis_state_lineage(
        algorithm_id="cost-basis-lot-state-transition",
        input_payload={
            "calculated_transactions": calculated_transactions,
            "trigger_transaction": trigger_payload,
            "transition_kind": transition_kind,
        },
        output_payload={
            "open_lot_states": {
                source_id: {
                    "cost_base": state.cost_base,
                    "cost_local": state.cost_local,
                    "quantity": state.quantity,
                }
                for source_id, state in open_lot_states.items()
            }
        },
    )
    return CostBasisStateTransitionEvidence(
        trigger_transaction_id=transaction.transaction_id,
        transition_kind=transition_kind,
        transition_lineage=transition_lineage,
    )
