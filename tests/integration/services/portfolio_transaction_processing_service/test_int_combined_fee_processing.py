from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    PositionHistory,
    PositionLotState,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    instrument_record,
    persist_and_process_booked_transaction,
    portfolio_record,
    process_booked_transaction,
    transaction_processing_test_context,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_combined_full_disposal_applies_fees_to_cash_and_cost_basis(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-FEE-01"
    security_id = "FO_EQ_COMBINED_FEE_01"
    buy_event = booked_transaction_event(
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
    sell_event = booked_transaction_event(
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
    async_db_session.add(portfolio_record(portfolio_id))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing Fee Equity",
            isin="SG0000000002",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)

    buy_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=buy_event,
        event_id="transactions.persisted-0-9201",
        correlation_id="corr-combined-fee-buy-01",
    )
    sell_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=sell_event,
        event_id="transactions.persisted-0-9202",
        correlation_id="corr-combined-fee-sell-01",
    )
    duplicate_sell_result = await process_booked_transaction(
        context=context,
        event=sell_event,
        event_id="transactions.persisted-0-9202",
        correlation_id="corr-combined-fee-sell-01",
    )

    assert buy_result.status is TransactionProcessingStatus.PROCESSED
    assert sell_result.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_sell_result.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
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
