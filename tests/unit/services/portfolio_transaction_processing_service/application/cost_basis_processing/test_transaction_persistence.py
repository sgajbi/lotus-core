"""Application tests for calculated transaction cost-basis persistence."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, call

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    AccruedIncomeOffsetStatePort,
    CostBasisLotStatePort,
    CostBasisPersistenceObservation,
    CostBasisPersistenceObserver,
    CostBasisPersistenceStage,
    CostBasisPersistenceStatus,
    CostBasisTransactionStatePort,
)

pytestmark = pytest.mark.asyncio

persist_cost_basis_transactions = cost_basis_processing.persist_cost_basis_transactions


def _calculated_transaction(
    transaction_id: str,
    *,
    transaction_type: str = "BUY",
    fee: Decimal = Decimal(0),
) -> CostBasisTransaction:
    return CostBasisTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-1",
        instrument_id="INST-1",
        security_id="SEC-1",
        transaction_type=transaction_type,
        transaction_date=datetime(2026, 1, 2),
        quantity=Decimal("4"),
        gross_transaction_amount=Decimal("48"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        fees={"brokerage": fee},
    )


def _booked_transaction(transaction: CostBasisTransaction) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction.transaction_id,
        portfolio_id=transaction.portfolio_id,
        instrument_id=transaction.instrument_id,
        security_id=transaction.security_id,
        transaction_date=transaction.transaction_date,
        transaction_type=transaction.transaction_type,
        quantity=transaction.quantity,
        price=Decimal("12"),
        gross_transaction_amount=transaction.gross_transaction_amount,
        trade_currency=transaction.trade_currency,
        currency=transaction.trade_currency,
    )


def _ports() -> tuple[
    AsyncMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    return (
        AsyncMock(spec=CostBasisTransactionStatePort),
        AsyncMock(spec=CostBasisLotStatePort),
        AsyncMock(spec=AccruedIncomeOffsetStatePort),
        AsyncMock(spec=CostBasisPersistenceObserver),
    )


async def test_backdated_persistence_updates_affected_suffix_and_returns_incoming_only() -> None:
    prior = _calculated_transaction("BUY-PRIOR")
    incoming = _calculated_transaction("BUY-BACKDATED")
    later = _calculated_transaction("SELL-LATER", transaction_type="SELL")
    repository, lot_states, income_offsets, observer = _ports()
    incoming_booked = _booked_transaction(incoming)
    later_booked = _booked_transaction(later)
    repository.apply_transaction_costs.side_effect = [incoming_booked, later_booked]

    persisted = await persist_cost_basis_transactions(
        processed=[prior, incoming, later],
        incoming_transaction_ids={incoming.transaction_id},
        transactions=repository,
        lot_states=lot_states,
        income_offsets=income_offsets,
        observer=observer,
    )

    assert [transaction.transaction_id for transaction in persisted] == [incoming.transaction_id]
    assert repository.apply_transaction_costs.await_args_list == [call(incoming), call(later)]
    assert repository.replace_transaction_cost_breakdown.await_args_list == [
        call(incoming),
        call(later),
    ]


async def test_persistence_rejects_timeline_without_incoming_transaction_before_writes() -> None:
    repository, lot_states, income_offsets, observer = _ports()

    with pytest.raises(
        ValueError,
        match="Processed transaction timeline omitted the incoming transaction",
    ):
        await persist_cost_basis_transactions(
            processed=[_calculated_transaction("BUY-PRIOR")],
            incoming_transaction_ids={"BUY-MISSING"},
            transactions=repository,
            lot_states=lot_states,
            income_offsets=income_offsets,
            observer=observer,
        )

    repository.apply_transaction_costs.assert_not_awaited()
    repository.replace_transaction_cost_breakdown.assert_not_awaited()
    observer.observe.assert_not_called()


async def test_persistence_supports_application_use_without_telemetry_adapter() -> None:
    transaction = _calculated_transaction("SELL-1", transaction_type="SELL")
    repository, lot_states, income_offsets, _ = _ports()
    repository.apply_transaction_costs.return_value = _booked_transaction(transaction)

    persisted = await persist_cost_basis_transactions(
        processed=[transaction],
        incoming_transaction_ids={transaction.transaction_id},
        transactions=repository,
        lot_states=lot_states,
        income_offsets=income_offsets,
    )

    assert persisted == (_booked_transaction(transaction),)


async def test_persistence_stops_before_child_writes_when_canonical_row_is_missing() -> None:
    transaction = _calculated_transaction("BUY-MISSING")
    repository, lot_states, income_offsets, observer = _ports()
    repository.apply_transaction_costs.return_value = None

    with pytest.raises(
        ValueError,
        match="Canonical transaction row was not found during cost persistence: BUY-MISSING",
    ):
        await persist_cost_basis_transactions(
            processed=[transaction],
            incoming_transaction_ids={transaction.transaction_id},
            transactions=repository,
            lot_states=lot_states,
            income_offsets=income_offsets,
            observer=observer,
        )

    repository.replace_transaction_cost_breakdown.assert_not_awaited()
    lot_states.upsert_buy_lot_state.assert_not_awaited()
    income_offsets.upsert_accrued_income_offset.assert_not_awaited()
    observer.observe.assert_called_once_with(
        CostBasisPersistenceObservation(
            transaction=transaction,
            stage=CostBasisPersistenceStage.TRANSACTION_COSTS,
            status=CostBasisPersistenceStatus.ATTEMPT,
        )
    )


@pytest.mark.parametrize(
    ("transaction_type", "fee", "persists_open_lot", "persists_accrued_income"),
    [
        ("BUY", Decimal("4.50"), True, True),
        ("SELL", Decimal(0), False, False),
        ("TRANSFER_IN", Decimal("1.25"), True, False),
    ],
)
async def test_persistence_applies_transaction_type_child_state_and_trade_fee(
    transaction_type: str,
    fee: Decimal,
    persists_open_lot: bool,
    persists_accrued_income: bool,
) -> None:
    transaction = _calculated_transaction(
        f"{transaction_type}-1",
        transaction_type=transaction_type,
        fee=fee,
    )
    repository, lot_states, income_offsets, observer = _ports()
    repository.apply_transaction_costs.return_value = _booked_transaction(transaction)

    persisted = await persist_cost_basis_transactions(
        processed=[transaction],
        incoming_transaction_ids={transaction.transaction_id},
        transactions=repository,
        lot_states=lot_states,
        income_offsets=income_offsets,
        observer=observer,
    )

    assert persisted[0].trade_fee == fee
    if persists_open_lot:
        lot_states.upsert_buy_lot_state.assert_awaited_once_with(transaction)
    else:
        lot_states.upsert_buy_lot_state.assert_not_awaited()
    if persists_accrued_income:
        income_offsets.upsert_accrued_income_offset.assert_awaited_once_with(transaction)
    else:
        income_offsets.upsert_accrued_income_offset.assert_not_awaited()

    observed_stages = [
        observation.stage
        for observation in (item.args[0] for item in observer.observe.call_args_list)
    ]
    assert observed_stages == [
        CostBasisPersistenceStage.TRANSACTION_COSTS,
        CostBasisPersistenceStage.TRANSACTION_COSTS,
        *(
            [CostBasisPersistenceStage.OPEN_LOT, CostBasisPersistenceStage.OPEN_LOT]
            if persists_open_lot
            else []
        ),
        *(
            [
                CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
                CostBasisPersistenceStage.ACCRUED_INCOME_OFFSET,
            ]
            if persists_accrued_income
            else []
        ),
    ]
    observed_statuses = [
        observation.status
        for observation in (item.args[0] for item in observer.observe.call_args_list)
    ]
    assert observed_statuses == [
        CostBasisPersistenceStatus.ATTEMPT,
        CostBasisPersistenceStatus.SUCCESS,
        *(
            [CostBasisPersistenceStatus.ATTEMPT, CostBasisPersistenceStatus.SUCCESS]
            if persists_open_lot
            else []
        ),
        *(
            [CostBasisPersistenceStatus.ATTEMPT, CostBasisPersistenceStatus.SUCCESS]
            if persists_accrued_income
            else []
        ),
    ]
