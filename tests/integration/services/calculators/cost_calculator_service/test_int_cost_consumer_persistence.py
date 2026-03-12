from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import OutboxEvent, Portfolio, ProcessedEvent
from portfolio_common.events import TransactionEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cost_calculator_service.app.consumer import (
    CostCalculatorConsumer,
)

pytestmark = pytest.mark.asyncio


async def test_adjustment_message_persists_outbox_and_idempotency(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add(
        Portfolio(
            portfolio_id="PORT-COST-INT-01",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="MODERATE",
            investment_time_horizon="MEDIUM_TERM",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id="CLIENT-COST-INT-01",
            is_leverage_allowed=False,
            status="ACTIVE",
        )
    )
    await async_db_session.commit()

    event = TransactionEvent(
        transaction_id="ADJ-COST-INT-01",
        portfolio_id="PORT-COST-INT-01",
        instrument_id="CASH",
        security_id="CASH",
        transaction_date=datetime(2026, 1, 5, 10, 0, 0),
        transaction_type="ADJUSTMENT",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("125.50"),
        trade_currency="USD",
        currency="USD",
    )
    msg = MagicMock()
    msg.value.return_value = event.model_dump_json().encode("utf-8")
    msg.topic.return_value = "raw_transactions_completed"
    msg.partition.return_value = 0
    msg.offset.return_value = 42
    msg.headers.return_value = [("correlation_id", b"corr-cost-int-01")]

    consumer = CostCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="raw_transactions_completed",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()

    async def override_session():
        yield async_db_session

    with patch(
        "src.services.calculators.cost_calculator_service.app.consumer.get_async_db_session",
        new=override_session,
    ):
        await consumer.process_message(msg)

    outbox_rows = (
        (
            await async_db_session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "ProcessedTransactionPersisted",
                    OutboxEvent.aggregate_id == "PORT-COST-INT-01",
                )
            )
        )
        .scalars()
        .all()
    )
    processed_rows = (
        (
            await async_db_session.execute(
                select(ProcessedEvent).where(
                    ProcessedEvent.event_id == "raw_transactions_completed-0-42",
                    ProcessedEvent.service_name == "cost-calculator",
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(outbox_rows) == 1
    assert outbox_rows[0].correlation_id == "corr-cost-int-01"
    assert outbox_rows[0].payload["transaction_id"] == "ADJ-COST-INT-01"
    assert len(processed_rows) == 1
    assert processed_rows[0].correlation_id == "corr-cost-int-01"
