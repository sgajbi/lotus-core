import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import FinancialReconciliationCompletedEvent

from src.services.pipeline_orchestrator_service.app.consumers import (
    financial_reconciliation_completion_consumer as consumer_module,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer() -> consumer_module.FinancialReconciliationCompletionConsumer:
    c = consumer_module.FinancialReconciliationCompletionConsumer(
        bootstrap_servers="mock_server",
        topic="portfolio_day.reconciliation.completed",
        group_id="test_group",
    )
    c._send_to_dlq_async = AsyncMock()
    return c


@pytest.fixture
def mock_event() -> FinancialReconciliationCompletedEvent:
    return FinancialReconciliationCompletedEvent(
        portfolio_id="PORT-CTRL-1",
        business_date=date(2026, 3, 8),
        epoch=2,
        outcome_status="REQUIRES_REPLAY",
        reconciliation_types=[
            "transaction_cashflow",
            "position_valuation",
            "timeseries_integrity",
        ],
        blocking_reconciliation_types=["transaction_cashflow"],
        run_ids={"transaction_cashflow": "recon-tx"},
        error_count=1,
        warning_count=0,
        correlation_id="corr-ctrl",
    )


@pytest.fixture
def mock_kafka_message(mock_event: FinancialReconciliationCompletedEvent) -> MagicMock:
    msg = MagicMock()
    msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    msg.key.return_value = b"PORT-CTRL-1"
    msg.topic.return_value = "portfolio_day.reconciliation.completed"
    msg.partition.return_value = 0
    msg.offset.return_value = 9
    msg.headers.return_value = []
    return msg


@pytest.fixture
def mock_handler():
    handler = MagicMock()
    handler.handle_reconciliation_completed = AsyncMock()

    with patch(
        "src.services.pipeline_orchestrator_service.app.consumers."
        "financial_reconciliation_completion_consumer.get_pipeline_stage_message_handler",
        return_value=handler,
    ):
        yield handler


async def test_completion_consumer_updates_orchestrator_stage_and_marks_idempotency(
    consumer: consumer_module.FinancialReconciliationCompletionConsumer,
    mock_kafka_message: MagicMock,
    mock_event: FinancialReconciliationCompletedEvent,
    mock_handler: MagicMock,
):
    await consumer.process_message(mock_kafka_message)

    mock_handler.handle_reconciliation_completed.assert_awaited_once_with(
        event_id="portfolio_day.reconciliation.completed-0-9",
        event=mock_event,
        correlation_id="corr-ctrl",
    )


async def test_completion_consumer_sends_invalid_payload_to_dlq(
    consumer: consumer_module.FinancialReconciliationCompletionConsumer,
):
    msg = MagicMock()
    msg.value.return_value = json.dumps({"portfolio_id": "bad"}).encode("utf-8")
    msg.key.return_value = b"bad"
    msg.topic.return_value = "portfolio_day.reconciliation.completed"
    msg.partition.return_value = 0
    msg.offset.return_value = 10
    msg.headers.return_value = []

    await consumer.process_message(msg)

    consumer._send_to_dlq_async.assert_awaited_once()


async def test_completion_consumer_preserves_payload_correlation_over_header_override(
    consumer: consumer_module.FinancialReconciliationCompletionConsumer,
    mock_kafka_message: MagicMock,
    mock_event: FinancialReconciliationCompletedEvent,
    mock_handler: MagicMock,
):
    mock_kafka_message.headers.return_value = [("correlation_id", b"header-corr")]

    await consumer.process_message(mock_kafka_message)

    mock_handler.handle_reconciliation_completed.assert_awaited_once_with(
        event_id="portfolio_day.reconciliation.completed-0-9",
        event=mock_event,
        correlation_id="corr-ctrl",
    )
