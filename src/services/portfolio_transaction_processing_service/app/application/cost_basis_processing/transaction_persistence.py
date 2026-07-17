"""Persist calculated transaction economics through framework-neutral ports."""

from dataclasses import replace
from decimal import Decimal

from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
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
)


async def persist_cost_basis_transactions(
    *,
    processed: list[CostBasisTransaction],
    incoming_transaction_ids: set[str],
    transactions: CostBasisTransactionStatePort,
    lot_states: CostBasisLotStatePort,
    income_offsets: AccruedIncomeOffsetStatePort,
    observer: CostBasisPersistenceObserver | None = None,
) -> tuple[BookedTransaction, ...]:
    """Persist the affected timeline suffix and return newly processed transactions."""

    first_affected_index = next(
        (
            index
            for index, transaction in enumerate(processed)
            if transaction.transaction_id in incoming_transaction_ids
        ),
        None,
    )
    if first_affected_index is None:
        raise ValueError("Processed transaction timeline omitted the incoming transaction")

    persistence_observer = observer or _NullCostBasisPersistenceObserver()
    newly_persisted: list[BookedTransaction] = []
    for transaction in processed[first_affected_index:]:
        persisted = await _persist_cost_basis_transaction(
            transaction=transaction,
            transactions=transactions,
            lot_states=lot_states,
            income_offsets=income_offsets,
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

    if transaction_lot_behavior(transaction.transaction_type) in LOT_OPENING_BEHAVIORS:
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

    if transaction.transaction_type == "BUY":
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
