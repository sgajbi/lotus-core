"""Persist calculated transaction economics through framework-neutral ports."""

from dataclasses import replace
from decimal import Decimal

from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
    CostBasisProcessingCheckpoint,
    CostBasisTransaction,
    transaction_lot_behavior,
)
from ...domain.transaction import BookedTransaction
from ...ports import (
    AccruedIncomeOffsetStatePort,
    CostBasisLotStatePort,
    CostBasisPersistenceObservation,
    CostBasisPersistenceObserver,
    CostBasisPersistenceStage,
    CostBasisPersistenceStatus,
    CostBasisTransactionStatePort,
    InitialOpeningCostStatePort,
)
from .persistence_scope import (
    CostBasisTransactionPersistenceScope,
    build_cost_basis_persistence_plan,
)


async def persist_cost_basis_transactions(
    *,
    processed: list[CostBasisTransaction],
    incoming_transaction_ids: set[str],
    transactions: CostBasisTransactionStatePort,
    lot_states: CostBasisLotStatePort,
    income_offsets: AccruedIncomeOffsetStatePort,
    initial_opening_state: InitialOpeningCostStatePort | None = None,
    initial_opening_checkpoint: CostBasisProcessingCheckpoint | None = None,
    observer: CostBasisPersistenceObserver | None = None,
    persistence_scope: CostBasisTransactionPersistenceScope = (
        CostBasisTransactionPersistenceScope.AFFECTED_SUFFIX
    ),
    missing_authority_transaction_ids: set[str] | frozenset[str] = frozenset(),
) -> tuple[BookedTransaction, ...]:
    """Persist governed timeline economics and return newly processed transactions."""

    persistence_observer = observer or _NullCostBasisPersistenceObserver()
    newly_persisted: list[BookedTransaction] = []
    persistence_plan = build_cost_basis_persistence_plan(
        processed=processed,
        incoming_transaction_ids=incoming_transaction_ids,
        scope=persistence_scope,
        missing_authority_transaction_ids=missing_authority_transaction_ids,
    )
    affected_transaction_ids = {
        transaction.transaction_id for transaction in persistence_plan.child_state_transactions
    }
    for transaction in persistence_plan.economics_transactions:
        persisted = await _persist_cost_basis_transaction(
            transaction=transaction,
            transactions=transactions,
            lot_states=lot_states,
            income_offsets=income_offsets,
            initial_opening_state=initial_opening_state,
            initial_opening_checkpoint=(
                initial_opening_checkpoint
                if transaction.transaction_id in incoming_transaction_ids
                else None
            ),
            persist_child_state=transaction.transaction_id in affected_transaction_ids,
            observer=persistence_observer,
        )
        if transaction.transaction_id in incoming_transaction_ids:
            newly_persisted.append(persisted)
    return tuple(newly_persisted)


async def _persist_cost_basis_transaction(
    *,
    transaction: CostBasisTransaction,
    transactions: CostBasisTransactionStatePort,
    lot_states: CostBasisLotStatePort,
    income_offsets: AccruedIncomeOffsetStatePort,
    initial_opening_state: InitialOpeningCostStatePort | None,
    initial_opening_checkpoint: CostBasisProcessingCheckpoint | None,
    persist_child_state: bool,
    observer: CostBasisPersistenceObserver,
) -> BookedTransaction:
    _observe(
        observer,
        transaction=transaction,
        stage=CostBasisPersistenceStage.TRANSACTION_COSTS,
        status=CostBasisPersistenceStatus.ATTEMPT,
    )
    persisted = await transactions.apply_transaction_costs_and_replace_breakdown(transaction)
    if persisted is None:
        raise ValueError(
            "Canonical transaction row was not found during cost persistence: "
            f"{transaction.transaction_id}"
        )
    _observe(
        observer,
        transaction=transaction,
        stage=CostBasisPersistenceStage.TRANSACTION_COSTS,
        status=CostBasisPersistenceStatus.SUCCESS,
    )

    persisted = replace(persisted, lot_restatement=transaction.lot_restatement)
    if not persist_child_state:
        return persisted

    if initial_opening_checkpoint is not None:
        await _persist_initial_opening_state(
            transaction=transaction,
            checkpoint=initial_opening_checkpoint,
            state=_require_initial_opening_state(initial_opening_state),
            observer=observer,
        )
    elif transaction_lot_behavior(transaction.transaction_type) in LOT_OPENING_BEHAVIORS:
        _observe(
            observer,
            transaction=transaction,
            stage=CostBasisPersistenceStage.OPEN_LOT,
            status=CostBasisPersistenceStatus.ATTEMPT,
        )
        await lot_states.upsert_buy_lot_state(transaction)
        _observe(
            observer,
            transaction=transaction,
            stage=CostBasisPersistenceStage.OPEN_LOT,
            status=CostBasisPersistenceStatus.SUCCESS,
        )

    if (
        normalize_transaction_control_code(transaction.transaction_type) == "BUY"
        and initial_opening_checkpoint is None
    ):
        _observe(
            observer,
            transaction=transaction,
            stage=CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
            status=CostBasisPersistenceStatus.ATTEMPT,
        )
        await income_offsets.upsert_accrued_income_offset(transaction)
        _observe(
            observer,
            transaction=transaction,
            stage=CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
            status=CostBasisPersistenceStatus.SUCCESS,
        )

    trade_fee = (
        transaction.fees.total_fees
        if transaction.fees is not None and transaction.fees.total_fees > Decimal(0)
        else Decimal(0)
    )
    return replace(persisted, trade_fee=trade_fee)


async def _persist_initial_opening_state(
    *,
    transaction: CostBasisTransaction,
    checkpoint: CostBasisProcessingCheckpoint,
    state: InitialOpeningCostStatePort,
    observer: CostBasisPersistenceObserver,
) -> None:
    if normalize_transaction_control_code(transaction.transaction_type) != "BUY":
        raise ValueError("Initial opening cost state requires a BUY transaction")
    for stage in (
        CostBasisPersistenceStage.OPEN_LOT,
        CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
    ):
        _observe(
            observer,
            transaction=transaction,
            stage=stage,
            status=CostBasisPersistenceStatus.ATTEMPT,
        )
    await state.persist_initial_opening_cost_state(
        transaction=transaction,
        checkpoint=checkpoint,
    )
    for stage in (
        CostBasisPersistenceStage.OPEN_LOT,
        CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
    ):
        _observe(
            observer,
            transaction=transaction,
            stage=stage,
            status=CostBasisPersistenceStatus.SUCCESS,
        )


def _observe(
    observer: CostBasisPersistenceObserver,
    *,
    transaction: CostBasisTransaction,
    stage: CostBasisPersistenceStage,
    status: CostBasisPersistenceStatus,
) -> None:
    observer.observe(
        CostBasisPersistenceObservation(
            transaction=transaction,
            stage=stage,
            status=status,
        )
    )


class _NullCostBasisPersistenceObserver:
    """Provide no-op observation for isolated application use."""

    def observe(self, observation: CostBasisPersistenceObservation) -> None:
        del observation


def _require_initial_opening_state(
    state: InitialOpeningCostStatePort | None,
) -> InitialOpeningCostStatePort:
    if state is None:
        raise ValueError("Initial opening cost-state persistence port is required")
    return state
