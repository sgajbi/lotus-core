from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    FxRate,
    Instrument,
    OutboxEvent,
    Portfolio,
    PositionHistory,
    PositionLotState,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    map_transaction_event,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    build_process_transaction_use_case,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_combined_buy_sell_preserves_lot_cashflow_and_position_results(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-LOT-01"
    security_id = "FO_EQ_COMBINED_01"
    buy_event = _transaction_event(
        transaction_id="BUY-COMBINED-LOT-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="420",
        price="100",
        gross_amount="42000",
    )
    sell_event = _transaction_event(
        transaction_id="SELL-COMBINED-LOT-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 2, 28, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="110",
        price="110",
        gross_amount="12100",
    )
    async_db_session.add(_portfolio(portfolio_id))
    async_db_session.add(
        Instrument(
            security_id=security_id,
            name="Combined Processing Equity",
            isin="SG0000000001",
            currency="USD",
            product_type="EQUITY",
            asset_class="Equity",
        )
    )
    async_db_session.add(_db_transaction(buy_event))
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    use_case = build_process_transaction_use_case(session_factory=session_factory)

    buy_result = await use_case.execute(
        map_transaction_event(
            buy_event,
            event_id="transactions.persisted-0-9101",
            correlation_id="corr-combined-buy-01",
        )
    )
    async_db_session.add(_db_transaction(sell_event))
    await async_db_session.commit()
    sell_result = await use_case.execute(
        map_transaction_event(
            sell_event,
            event_id="transactions.persisted-0-9102",
            correlation_id="corr-combined-sell-01",
        )
    )

    assert buy_result.status is TransactionProcessingStatus.PROCESSED
    assert sell_result.status is TransactionProcessingStatus.PROCESSED
    assert buy_result.cashflow_record_count == sell_result.cashflow_record_count == 1
    assert buy_result.position_record_count == sell_result.position_record_count == 1

    async with session_factory() as verification_session:
        lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == buy_event.transaction_id
                )
            )
        ).scalar_one()
        persisted_sell = (
            await verification_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == sell_event.transaction_id
                )
            )
        ).scalar_one()
        cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(Cashflow.portfolio_id == portfolio_id)
                    .order_by(Cashflow.cashflow_date)
                )
            )
            .scalars()
            .all()
        )
        positions = (
            (
                await verification_session.execute(
                    select(PositionHistory)
                    .where(
                        PositionHistory.portfolio_id == portfolio_id,
                        PositionHistory.security_id == security_id,
                    )
                    .order_by(PositionHistory.position_date)
                )
            )
            .scalars()
            .all()
        )
        outbox_rows = (
            (
                await verification_session.execute(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == portfolio_id)
                )
            )
            .scalars()
            .all()
        )

    assert lot.original_quantity == Decimal("420")
    assert lot.open_quantity == Decimal("310")
    assert persisted_sell.net_cost == Decimal("-11000")
    assert persisted_sell.realized_gain_loss == Decimal("1100")
    assert [(row.classification, row.amount) for row in cashflows] == [
        ("INVESTMENT_OUTFLOW", Decimal("-42000")),
        ("INVESTMENT_INFLOW", Decimal("12100")),
    ]
    assert [(row.quantity, row.cost_basis) for row in positions] == [
        (Decimal("420"), Decimal("42000")),
        (Decimal("310"), Decimal("31000")),
    ]
    assert sorted(row.event_type for row in outbox_rows) == [
        "CashflowCalculated",
        "CashflowCalculated",
        "ProcessedTransactionPersisted",
        "ProcessedTransactionPersisted",
    ]


async def test_combined_full_disposal_applies_fees_to_cash_and_cost_basis(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-FEE-01"
    security_id = "FO_EQ_COMBINED_FEE_01"
    buy_event = _transaction_event(
        transaction_id="BUY-COMBINED-FEE-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="15",
        price="100",
        gross_amount="1500",
        trade_fee="7.50",
    )
    sell_event = _transaction_event(
        transaction_id="SELL-COMBINED-FEE-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="15",
        price="110",
        gross_amount="1650",
        trade_fee="5",
    )
    async_db_session.add(_portfolio(portfolio_id))
    async_db_session.add(
        Instrument(
            security_id=security_id,
            name="Combined Processing Fee Equity",
            isin="SG0000000002",
            currency="USD",
            product_type="EQUITY",
            asset_class="Equity",
        )
    )
    async_db_session.add(_db_transaction(buy_event))
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    use_case = build_process_transaction_use_case(session_factory=session_factory)

    buy_command = map_transaction_event(
        buy_event,
        event_id="transactions.persisted-0-9201",
        correlation_id="corr-combined-fee-buy-01",
    )
    buy_result = await use_case.execute(buy_command)
    async_db_session.add(_db_transaction(sell_event))
    await async_db_session.commit()
    sell_command = map_transaction_event(
        sell_event,
        event_id="transactions.persisted-0-9202",
        correlation_id="corr-combined-fee-sell-01",
    )
    sell_result = await use_case.execute(sell_command)
    duplicate_sell_result = await use_case.execute(sell_command)

    assert buy_result.status is TransactionProcessingStatus.PROCESSED
    assert sell_result.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_sell_result.status is TransactionProcessingStatus.DUPLICATE

    async with session_factory() as verification_session:
        lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == buy_event.transaction_id
                )
            )
        ).scalar_one()
        persisted_transactions = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id.in_(
                                [buy_event.transaction_id, sell_event.transaction_id]
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        transaction_costs = (
            (
                await verification_session.execute(
                    select(TransactionCost).order_by(TransactionCost.transaction_id)
                )
            )
            .scalars()
            .all()
        )
        cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(Cashflow.portfolio_id == portfolio_id)
                    .order_by(Cashflow.cashflow_date)
                )
            )
            .scalars()
            .all()
        )
        positions = (
            (
                await verification_session.execute(
                    select(PositionHistory)
                    .where(
                        PositionHistory.portfolio_id == portfolio_id,
                        PositionHistory.security_id == security_id,
                    )
                    .order_by(PositionHistory.position_date)
                )
            )
            .scalars()
            .all()
        )

    persisted_buy = persisted_transactions[buy_event.transaction_id]
    persisted_sell = persisted_transactions[sell_event.transaction_id]
    assert persisted_buy.net_cost == Decimal("1507.50")
    assert persisted_sell.net_cost == Decimal("-1507.50")
    assert persisted_sell.realized_gain_loss == Decimal("137.50")
    assert lot.original_quantity == Decimal("15")
    assert lot.open_quantity == Decimal("0")
    assert lot.lot_cost_base == Decimal("1507.50")
    assert [(row.transaction_id, row.fee_type, row.amount) for row in transaction_costs] == [
        (buy_event.transaction_id, "brokerage", Decimal("7.50")),
        (sell_event.transaction_id, "brokerage", Decimal("5")),
    ]
    assert [(row.classification, row.amount) for row in cashflows] == [
        ("INVESTMENT_OUTFLOW", Decimal("-1507.50")),
        ("INVESTMENT_INFLOW", Decimal("1645")),
    ]
    assert [(row.quantity, row.cost_basis) for row in positions] == [
        (Decimal("15"), Decimal("1507.50")),
        (Decimal("0"), Decimal("0")),
    ]


async def test_combined_cross_currency_buy_uses_effective_fx_rate(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-FX-01"
    security_id = "FO_EQ_COMBINED_FX_01"
    transaction_date = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    event = _transaction_event(
        transaction_id="BUY-COMBINED-FX-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=transaction_date,
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_amount="1000",
        trade_fee="10",
        trade_currency="EUR",
    )
    async_db_session.add(_portfolio(portfolio_id, base_currency="SGD"))
    async_db_session.add(
        Instrument(
            security_id=security_id,
            name="Combined Processing Cross Currency Equity",
            isin="SG0000000003",
            currency="EUR",
            product_type="EQUITY",
            asset_class="Equity",
        )
    )
    async_db_session.add_all(
        [
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 5, 1),
                rate=Decimal("1.40"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 5, 9),
                rate=Decimal("1.45"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 5, 11),
                rate=Decimal("1.50"),
            ),
        ]
    )
    async_db_session.add(_db_transaction(event))
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    use_case = build_process_transaction_use_case(session_factory=session_factory)

    result = await use_case.execute(
        map_transaction_event(
            event,
            event_id="transactions.persisted-0-9301",
            correlation_id="corr-combined-fx-buy-01",
        )
    )

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert result.cashflow_record_count == 1
    assert result.position_record_count == 1

    async with session_factory() as verification_session:
        persisted_transaction = (
            await verification_session.execute(
                select(DBTransaction).where(DBTransaction.transaction_id == event.transaction_id)
            )
        ).scalar_one()
        lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == event.transaction_id
                )
            )
        ).scalar_one()
        transaction_cost = (
            await verification_session.execute(
                select(TransactionCost).where(
                    TransactionCost.transaction_id == event.transaction_id
                )
            )
        ).scalar_one()
        cashflow = (
            await verification_session.execute(
                select(Cashflow).where(Cashflow.transaction_id == event.transaction_id)
            )
        ).scalar_one()
        position = (
            await verification_session.execute(
                select(PositionHistory).where(
                    PositionHistory.transaction_id == event.transaction_id
                )
            )
        ).scalar_one()

    assert persisted_transaction.transaction_fx_rate == Decimal("1.45")
    assert persisted_transaction.net_cost_local == Decimal("1010")
    assert persisted_transaction.net_cost == Decimal("1464.50")
    assert lot.lot_cost_local == Decimal("1010")
    assert lot.lot_cost_base == Decimal("1464.50")
    assert (transaction_cost.fee_type, transaction_cost.amount, transaction_cost.currency) == (
        "brokerage",
        Decimal("10"),
        "EUR",
    )
    assert (cashflow.amount, cashflow.currency) == (Decimal("-1010"), "EUR")
    assert (position.cost_basis, position.cost_basis_local) == (
        Decimal("1464.50"),
        Decimal("1010"),
    )


def _portfolio(portfolio_id: str, *, base_currency: str = "USD") -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        open_date=date(2025, 1, 1),
        risk_exposure="MODERATE",
        investment_time_horizon="MEDIUM_TERM",
        portfolio_type="DISCRETIONARY",
        booking_center_code="SG",
        client_id="CLIENT-COMBINED-LOT-01",
        is_leverage_allowed=False,
        status="ACTIVE",
    )


def _transaction_event(
    *,
    transaction_id: str,
    portfolio_id: str,
    security_id: str,
    transaction_date: datetime,
    transaction_type: str,
    quantity: str,
    price: str,
    gross_amount: str,
    trade_fee: str = "0",
    trade_currency: str = "USD",
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        quantity=Decimal(quantity),
        price=Decimal(price),
        gross_transaction_amount=Decimal(gross_amount),
        trade_fee=Decimal(trade_fee),
        trade_currency=trade_currency,
        currency=trade_currency,
    )


def _db_transaction(event: TransactionEvent) -> DBTransaction:
    return DBTransaction(
        transaction_id=event.transaction_id,
        portfolio_id=event.portfolio_id,
        instrument_id=event.instrument_id,
        security_id=event.security_id,
        transaction_date=event.transaction_date,
        transaction_type=event.transaction_type,
        quantity=event.quantity,
        price=event.price,
        gross_transaction_amount=event.gross_transaction_amount,
        trade_fee=event.trade_fee,
        trade_currency=event.trade_currency,
        currency=event.currency,
    )
