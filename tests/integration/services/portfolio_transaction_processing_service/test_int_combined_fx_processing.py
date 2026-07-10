from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    FxRate,
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
    transaction_processing_test_context,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_combined_cross_currency_buy_uses_effective_fx_rate(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-FX-01"
    security_id = "FO_EQ_COMBINED_FX_01"
    transaction_date = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    event = booked_transaction_event(
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
    async_db_session.add(portfolio_record(portfolio_id, base_currency="SGD"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing Cross Currency Equity",
            isin="SG0000000003",
            currency="EUR",
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
    context = transaction_processing_test_context(async_db_session)

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-9301",
        correlation_id="corr-combined-fx-buy-01",
    )

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert result.cashflow_record_count == 1
    assert result.position_record_count == 1

    async with context.session_factory() as verification_session:
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
