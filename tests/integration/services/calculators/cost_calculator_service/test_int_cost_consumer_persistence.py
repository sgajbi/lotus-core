from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    Transaction as DBTransaction,
    OutboxEvent,
    Portfolio,
    PositionLotState,
    ProcessedEvent,
)
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
    msg.topic.return_value = "transactions.persisted"
    msg.partition.return_value = 0
    msg.offset.return_value = 42
    msg.headers.return_value = [("correlation_id", b"corr-cost-int-01")]

    consumer = CostCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.persisted",
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
                    ProcessedEvent.event_id == "transactions.persisted-0-42",
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


async def test_buy_then_sell_processing_reconciles_open_lot_quantity(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add(
        Portfolio(
            portfolio_id="PORT-COST-INT-LOT-01",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="MODERATE",
            investment_time_horizon="MEDIUM_TERM",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id="CLIENT-COST-INT-LOT-01",
            is_leverage_allowed=False,
            status="ACTIVE",
        )
    )
    async_db_session.add_all(
        [
            DBTransaction(
                transaction_id="BUY-COST-INT-LOT-01",
                portfolio_id="PORT-COST-INT-LOT-01",
                instrument_id="FO_EQ_AAPL_US",
                security_id="FO_EQ_AAPL_US",
                transaction_date=datetime(2026, 1, 10, 10, 0, 0),
                transaction_type="BUY",
                quantity=Decimal("420"),
                price=Decimal("100"),
                gross_transaction_amount=Decimal("42000"),
                trade_currency="USD",
                currency="USD",
            ),
            DBTransaction(
                transaction_id="SELL-COST-INT-LOT-01",
                portfolio_id="PORT-COST-INT-LOT-01",
                instrument_id="FO_EQ_AAPL_US",
                security_id="FO_EQ_AAPL_US",
                transaction_date=datetime(2026, 2, 28, 10, 0, 0),
                transaction_type="SELL",
                quantity=Decimal("110"),
                price=Decimal("110"),
                gross_transaction_amount=Decimal("12100"),
                trade_currency="USD",
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()

    def build_message(event: TransactionEvent, *, offset: int) -> MagicMock:
        msg = MagicMock()
        msg.value.return_value = event.model_dump_json().encode("utf-8")
        msg.topic.return_value = "transactions.persisted"
        msg.partition.return_value = 0
        msg.offset.return_value = offset
        msg.headers.return_value = [("correlation_id", f"corr-lot-{offset}".encode("utf-8"))]
        return msg

    buy_event = TransactionEvent(
        transaction_id="BUY-COST-INT-LOT-01",
        portfolio_id="PORT-COST-INT-LOT-01",
        instrument_id="FO_EQ_AAPL_US",
        security_id="FO_EQ_AAPL_US",
        transaction_date=datetime(2026, 1, 10, 10, 0, 0),
        transaction_type="BUY",
        quantity=Decimal("420"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("42000"),
        trade_currency="USD",
        currency="USD",
    )
    sell_event = TransactionEvent(
        transaction_id="SELL-COST-INT-LOT-01",
        portfolio_id="PORT-COST-INT-LOT-01",
        instrument_id="FO_EQ_AAPL_US",
        security_id="FO_EQ_AAPL_US",
        transaction_date=datetime(2026, 2, 28, 10, 0, 0),
        transaction_type="SELL",
        quantity=Decimal("110"),
        price=Decimal("110"),
        gross_transaction_amount=Decimal("12100"),
        trade_currency="USD",
        currency="USD",
    )

    consumer = CostCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.persisted",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()

    async def override_session():
        yield async_db_session

    with patch(
        "src.services.calculators.cost_calculator_service.app.consumer.get_async_db_session",
        new=override_session,
    ):
        await consumer.process_message(build_message(buy_event, offset=100))
        await consumer.process_message(build_message(sell_event, offset=101))

    lot = (
        (
            await async_db_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == "BUY-COST-INT-LOT-01"
                )
            )
        )
        .scalars()
        .one()
    )
    sell_txn = (
        (
            await async_db_session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "ProcessedTransactionPersisted",
                    OutboxEvent.aggregate_id == "PORT-COST-INT-LOT-01",
                )
            )
        )
        .scalars()
        .all()
    )
    sell_payload = next(
        row.payload for row in sell_txn if row.payload["transaction_id"] == "SELL-COST-INT-LOT-01"
    )

    assert lot.original_quantity == Decimal("420")
    assert lot.open_quantity == Decimal("310")
    assert Decimal(sell_payload["net_cost"]) == Decimal("-11000")
    assert Decimal(sell_payload["realized_gain_loss"]) == Decimal("1100")
    consumer._send_to_dlq_async.assert_not_awaited()
