"""Reconcile generated settlement cash against persisted product cashflows."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import Cashflow
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


@pytest.mark.parametrize(
    (
        "transaction_type",
        "gross_amount",
        "quantity",
        "price",
        "expected_settlement",
        "domain_fields",
    ),
    [
        ("SELL", "1200", "10", "120", "1198", {}),
        (
            "DIVIDEND",
            "100",
            "0",
            "0",
            "88",
            {"withholding_tax_amount": Decimal("10")},
        ),
        (
            "INTEREST",
            "100",
            "0",
            "0",
            "85",
            {
                "withholding_tax_amount": Decimal("10"),
                "other_interest_deductions_amount": Decimal("3"),
                "net_interest_amount": Decimal("87"),
                "interest_direction": "INCOME",
            },
        ),
    ],
)
async def test_generated_cash_leg_and_product_cashflow_persist_equal_settlement(
    clean_db,
    async_db_session: AsyncSession,
    transaction_type: str,
    gross_amount: str,
    quantity: str,
    price: str,
    expected_settlement: str,
    domain_fields: dict[str, object],
) -> None:
    portfolio_id = f"PORT-GENERATED-{transaction_type}-01"
    security_id = f"SEC-GENERATED-{transaction_type}-01"
    transaction_id = f"{transaction_type}-GENERATED-SETTLEMENT-01"
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                security_id,
                name=f"Generated {transaction_type} settlement instrument",
                isin=f"SG000000{transaction_type[:2]}01",
                currency="USD",
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)

    if transaction_type == "SELL":
        opening_buy = booked_transaction_event(
            transaction_id="BUY-GENERATED-SELL-OPENING-01",
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
            settlement_date=datetime(2026, 4, 3, 9, 0, tzinfo=timezone.utc),
            transaction_type="BUY",
            quantity="10",
            price="100",
            gross_amount="1000",
        )
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=opening_buy,
            event_id="transactions.persisted-0-generated-opening",
            correlation_id="corr-generated-opening",
        )

    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=quantity,
        price=price,
        gross_amount=gross_amount,
        trade_fee="99",
        brokerage=Decimal("1.25"),
        stamp_duty=Decimal("0.75"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-001",
        settlement_cash_instrument_id="CASH-USD",
        **domain_fields,
    )

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id=f"transactions.persisted-0-{transaction_type.lower()}-generated",
        correlation_id=f"corr-{transaction_type.lower()}-generated",
    )

    cash_leg_id = f"{transaction_id}-CASHLEG"
    async with context.session_factory() as verification_session:
        persisted_transactions = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id.in_([transaction_id, cash_leg_id])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(Cashflow.transaction_id.in_([transaction_id, cash_leg_id]))
                    .order_by(Cashflow.transaction_id)
                )
            )
            .scalars()
            .all()
        )

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert result.processed_transaction_ids == (transaction_id, cash_leg_id)
    assert result.cashflow_record_count == 2
    assert persisted_transactions[transaction_id].external_cash_transaction_id == cash_leg_id
    generated_cash_leg = persisted_transactions[cash_leg_id]
    assert generated_cash_leg.gross_transaction_amount == Decimal(expected_settlement)
    assert generated_cash_leg.movement_direction == "INFLOW"
    assert generated_cash_leg.originating_transaction_id == transaction_id
    assert [cashflow.amount for cashflow in cashflows] == [
        Decimal(expected_settlement),
        Decimal(expected_settlement),
    ]
    assert len({cashflow.economic_event_id for cashflow in cashflows}) == 1
    assert len({cashflow.linked_transaction_group_id for cashflow in cashflows}) == 1
