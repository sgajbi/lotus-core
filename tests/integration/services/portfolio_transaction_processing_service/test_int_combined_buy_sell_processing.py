from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    OutboxEvent,
    PositionHistory,
    PositionLotState,
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
    transaction_processing_test_context,
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
    buy_event = booked_transaction_event(
        transaction_id="BUY-COMBINED-LOT-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="420",
        price="100",
        gross_amount="42000",
    )
    sell_event = booked_transaction_event(
        transaction_id="SELL-COMBINED-LOT-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 2, 28, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="110",
        price="110",
        gross_amount="12100",
    )
    async_db_session.add(portfolio_record(portfolio_id))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing Equity",
            isin="SG0000000001",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)

    buy_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=buy_event,
        event_id="transactions.persisted-0-9101",
        correlation_id="corr-combined-buy-01",
    )
    sell_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=sell_event,
        event_id="transactions.persisted-0-9102",
        correlation_id="corr-combined-sell-01",
    )

    assert buy_result.status is TransactionProcessingStatus.PROCESSED
    assert sell_result.status is TransactionProcessingStatus.PROCESSED
    assert buy_result.cashflow_record_count == sell_result.cashflow_record_count == 1
    assert buy_result.position_record_count == sell_result.position_record_count == 1

    async with context.session_factory() as verification_session:
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
    assert lot.lot_cost_local == Decimal("31000")
    assert lot.lot_cost_base == Decimal("31000")
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
