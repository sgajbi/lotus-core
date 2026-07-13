"""Prove INTEREST settlement economics through the PostgreSQL processing lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import Cashflow, OutboxEvent, PositionHistory
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


async def test_explicit_and_derived_interest_persist_equal_settlement_cash(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-INTEREST-01"
    security_id = "FO_BOND_INTEREST_01"
    derived_event = booked_transaction_event(
        transaction_id="INTEREST-DERIVED-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
        transaction_type="INTEREST",
        quantity="0",
        price="0",
        gross_amount="120",
        trade_fee="2",
        withholding_tax_amount=Decimal("10"),
        other_interest_deductions_amount=Decimal("3"),
        interest_direction="INCOME",
    )
    explicit_event = derived_event.model_copy(
        update={
            "transaction_id": "INTEREST-EXPLICIT-01",
            "transaction_date": datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
            "settlement_date": datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc),
            "net_interest_amount": Decimal("107"),
        }
    )
    bond = instrument_record(
        security_id,
        name="Private Bank USD Income Bond",
        isin="US0000007501",
        currency="USD",
    )
    bond.product_type = "BOND"
    bond.asset_class = "Fixed Income"
    async_db_session.add_all([portfolio_record(portfolio_id), bond])
    context = transaction_processing_test_context(async_db_session)

    derived_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=derived_event,
        event_id="transactions.persisted-0-7501",
        correlation_id="corr-interest-derived-01",
    )
    explicit_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=explicit_event,
        event_id="transactions.persisted-0-7502",
        correlation_id="corr-interest-explicit-01",
    )

    transaction_ids = (derived_event.transaction_id, explicit_event.transaction_id)
    async with context.session_factory() as verification_session:
        persisted_transactions = (
            (
                await verification_session.execute(
                    select(DBTransaction)
                    .where(DBTransaction.transaction_id.in_(transaction_ids))
                    .order_by(DBTransaction.transaction_id)
                )
            )
            .scalars()
            .all()
        )
        cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(Cashflow.transaction_id.in_(transaction_ids))
                    .order_by(Cashflow.transaction_id)
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

    assert derived_result.status is TransactionProcessingStatus.PROCESSED
    assert explicit_result.status is TransactionProcessingStatus.PROCESSED
    assert derived_result.cashflow_record_count == explicit_result.cashflow_record_count == 1
    assert [(row.transaction_id, row.net_interest_amount) for row in persisted_transactions] == [
        ("INTEREST-DERIVED-01", None),
        ("INTEREST-EXPLICIT-01", Decimal("107")),
    ]
    assert [(row.transaction_id, row.amount) for row in cashflows] == [
        ("INTEREST-DERIVED-01", Decimal("105")),
        ("INTEREST-EXPLICIT-01", Decimal("105")),
    ]
    assert {(row.quantity, row.cost_basis) for row in positions} == {(Decimal(0), Decimal(0))}
    assert sorted(row.event_type for row in outbox_rows) == [
        "CashflowCalculated",
        "CashflowCalculated",
        "ProcessedTransactionPersisted",
        "ProcessedTransactionPersisted",
    ]
