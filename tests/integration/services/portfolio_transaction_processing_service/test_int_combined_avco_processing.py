from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    AverageCostPoolState,
    Cashflow,
    PositionHistory,
    PositionLotState,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.transaction_domain import SELL_AVCO_POLICY_ID
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


async def test_combined_avco_disposal_reconciles_pooled_and_source_cost_basis(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-AVCO-01"
    security_id = "FO_EQ_COMBINED_AVCO_01"
    first_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-AVCO-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    second_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-AVCO-02",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="12",
        gross_amount="1200",
    )
    disposal = booked_transaction_event(
        transaction_id="SELL-COMBINED-AVCO-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="50",
        price="15",
        gross_amount="750",
    )
    async_db_session.add(portfolio_record(portfolio_id, cost_basis_method="AVCO"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing AVCO Equity",
            isin="SG0000000004",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)

    first_buy_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=first_buy,
        event_id="transactions.persisted-0-9401",
        correlation_id="corr-combined-avco-buy-01",
    )
    second_buy_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=second_buy,
        event_id="transactions.persisted-0-9402",
        correlation_id="corr-combined-avco-buy-02",
    )
    disposal_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=disposal,
        event_id="transactions.persisted-0-9403",
        correlation_id="corr-combined-avco-sell-01",
    )
    duplicate_disposal_result = await process_booked_transaction(
        context=context,
        event=disposal,
        event_id="transactions.persisted-0-9403",
        correlation_id="corr-combined-avco-sell-01",
    )

    assert first_buy_result.status is TransactionProcessingStatus.PROCESSED
    assert second_buy_result.status is TransactionProcessingStatus.PROCESSED
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
                    .order_by(PositionLotState.source_transaction_id)
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
        pool_state = (
            await verification_session.execute(
                select(AverageCostPoolState).where(
                    AverageCostPoolState.portfolio_id == portfolio_id,
                    AverageCostPoolState.security_id == security_id,
                )
            )
        ).scalar_one()

    assert persisted_disposal.calculation_policy_id == SELL_AVCO_POLICY_ID
    assert persisted_disposal.net_cost == Decimal("-550")
    assert persisted_disposal.realized_gain_loss == Decimal("200")
    assert [
        (
            lot.source_transaction_id,
            lot.open_quantity,
            lot.lot_cost_local,
            lot.lot_cost_base,
        )
        for lot in source_lots
    ] == [
        (first_buy.transaction_id, Decimal("75"), Decimal("750"), Decimal("750")),
        (second_buy.transaction_id, Decimal("75"), Decimal("900"), Decimal("900")),
    ]
    assert sum(lot.open_quantity for lot in source_lots) == Decimal("150")
    assert sum(lot.lot_cost_base for lot in source_lots) == Decimal("1650")
    assert pool_state.pool_quantity == Decimal("150")
    assert pool_state.pool_cost_local == Decimal("1650")
    assert pool_state.pool_cost_base == Decimal("1650")
    assert pool_state.representative_source_transaction_id == second_buy.transaction_id
    assert pool_state.state_version == "avco-pool-v1"
    assert [(cashflow.classification, cashflow.amount) for cashflow in cashflows] == [
        ("INVESTMENT_OUTFLOW", Decimal("-1000")),
        ("INVESTMENT_OUTFLOW", Decimal("-1200")),
        ("INVESTMENT_INFLOW", Decimal("750")),
    ]
    assert [
        (position.quantity, position.cost_basis, position.cost_basis_local)
        for position in positions
    ] == [
        (Decimal("100"), Decimal("1000"), Decimal("1000")),
        (Decimal("200"), Decimal("2200"), Decimal("2200")),
        (Decimal("150"), Decimal("1650"), Decimal("1650")),
    ]
