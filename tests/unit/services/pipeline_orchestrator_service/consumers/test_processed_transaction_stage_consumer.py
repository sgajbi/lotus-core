from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import GOVERNED_EVENT_SCHEMA_VERSION, TransactionEvent

from src.services.pipeline_orchestrator_service.app.consumers import (
    processed_transaction_stage_consumer as consumer_module,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer() -> consumer_module.ProcessedTransactionStageConsumer:
    c = consumer_module.ProcessedTransactionStageConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.processed",
        group_id="test_group",
    )
    c._send_to_dlq_async = AsyncMock()
    return c


@pytest.fixture
def mock_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-PIPE-CONSUMER-1",
        portfolio_id="PORT-PIPE-1",
        instrument_id="INST-PIPE-1",
        security_id="SEC-PIPE-1",
        transaction_date=datetime(2026, 3, 7, 10, 0, 0),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        epoch=0,
        event_type="ProcessedTransactionPersisted",
        schema_version=GOVERNED_EVENT_SCHEMA_VERSION,
    )


@pytest.fixture
def mock_kafka_message(mock_event: TransactionEvent) -> MagicMock:
    msg = MagicMock()
    msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    msg.key.return_value = b"TXN-PIPE-CONSUMER-1"
    msg.topic.return_value = "transactions.processed"
    msg.partition.return_value = 1
    msg.offset.return_value = 5
    msg.headers.return_value = [("correlation_id", b"corr-pipeline-consumer")]
    return msg


@pytest.fixture
def mock_handler():
    handler = MagicMock()
    handler.handle_processed_transaction = AsyncMock()

    with patch(
        "src.services.pipeline_orchestrator_service.app.consumers."
        "processed_transaction_stage_consumer.get_pipeline_stage_message_handler",
        return_value=handler,
    ):
        yield handler


async def test_processed_transaction_consumer_registers_stage_and_marks_idempotency(
    consumer: consumer_module.ProcessedTransactionStageConsumer,
    mock_kafka_message: MagicMock,
    mock_event: TransactionEvent,
    mock_handler: MagicMock,
):
    await consumer.process_message(mock_kafka_message)

    mock_handler.handle_processed_transaction.assert_awaited_once_with(
        event_id="transactions.processed-1-5",
        event=mock_event,
        correlation_id="corr-pipeline-consumer",
    )


async def test_processed_transaction_consumer_sends_invalid_payload_to_dlq(
    consumer: consumer_module.ProcessedTransactionStageConsumer,
):
    msg = MagicMock()
    msg.value.return_value = b"{not-json"
    msg.key.return_value = b"bad"
    msg.topic.return_value = "transactions.processed"
    msg.partition.return_value = 1
    msg.offset.return_value = 6
    msg.headers.return_value = []

    await consumer.process_message(msg)

    consumer._send_to_dlq_async.assert_awaited_once()
