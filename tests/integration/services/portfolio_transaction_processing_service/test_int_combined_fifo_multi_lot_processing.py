from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import Cashflow, PositionHistory, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    SELL_FIFO_POLICY_ID,
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


async def test_combined_fifo_disposal_exhausts_oldest_lot_before_next_lot(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-FIFO-MULTI-01"
    security_id = "FO_EQ_COMBINED_FIFO_MULTI_01"
    oldest_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-FIFO-MULTI-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    newest_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-FIFO-MULTI-02",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="50",
        price="12",
        gross_amount="600",
    )
    disposal = booked_transaction_event(
        transaction_id="SELL-COMBINED-FIFO-MULTI-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="120",
        price="15",
        gross_amount="1800",
    )
    async_db_session.add(portfolio_record(portfolio_id, cost_basis_method="FIFO"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing FIFO Multi Lot Equity",
            isin="SG0000000005",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)

    oldest_buy_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=oldest_buy,
        event_id="transactions.persisted-0-9501",
        correlation_id="corr-combined-fifo-buy-01",
    )
    newest_buy_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=newest_buy,
        event_id="transactions.persisted-0-9502",
        correlation_id="corr-combined-fifo-buy-02",
    )
    disposal_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=disposal,
        event_id="transactions.persisted-0-9503",
        correlation_id="corr-combined-fifo-sell-01",
    )
    duplicate_disposal_result = await process_booked_transaction(
        context=context,
        event=disposal,
        event_id="transactions.persisted-0-9503",
        correlation_id="corr-combined-fifo-sell-01",
    )

    assert oldest_buy_result.status is TransactionProcessingStatus.PROCESSED
    assert newest_buy_result.status is TransactionProcessingStatus.PROCESSED
    assert disposal_result.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_disposal_result.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        persisted_disposal = (
            await verification_session.execute(
                select(DBTransaction).where(DBTransaction.transaction_id == disposal.transaction_id)
            )
        ).scalar_one()
        source_lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.portfolio_id == portfolio_id)
                    .order_by(PositionLotState.acquisition_date)
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

    assert persisted_disposal.calculation_policy_id == SELL_FIFO_POLICY_ID
    assert persisted_disposal.net_cost == Decimal("-1240")
    assert persisted_disposal.realized_gain_loss == Decimal("560")
    assert [
        (
            lot.source_transaction_id,
            lot.open_quantity,
            lot.lot_cost_local,
            lot.lot_cost_base,
        )
        for lot in source_lots
    ] == [
        (oldest_buy.transaction_id, Decimal("0"), Decimal("0"), Decimal("0")),
        (newest_buy.transaction_id, Decimal("30"), Decimal("360"), Decimal("360")),
    ]
    assert sum(lot.open_quantity for lot in source_lots) == Decimal("30")
    assert sum(lot.lot_cost_base for lot in source_lots) == Decimal("360")
    assert [(cashflow.classification, cashflow.amount) for cashflow in cashflows] == [
        ("INVESTMENT_OUTFLOW", Decimal("-1000")),
        ("INVESTMENT_OUTFLOW", Decimal("-600")),
        ("INVESTMENT_INFLOW", Decimal("1800")),
    ]
    assert [
        (position.quantity, position.cost_basis, position.cost_basis_local)
        for position in positions
    ] == [
        (Decimal("100"), Decimal("1000"), Decimal("1000")),
        (Decimal("150"), Decimal("1600"), Decimal("1600")),
        (Decimal("30"), Decimal("360"), Decimal("360")),
    ]
