# tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_calculator.app.consumers.transaction_event_consumer import (
    TransactionEventConsumer,
)
from src.services.calculators.position_calculator.app.repositories.position_repository import (
    PositionRepository,
)
from tests.unit.test_support.async_session_iter import make_single_session_getter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def position_consumer():
    """Provides a clean instance of the consumer for each test."""
    consumer = TransactionEventConsumer(
        bootstrap_servers="mock_server",
        topic="processed_transactions_completed",
        group_id="test_group",
        dlq_topic="test.dlq",
    )
    # Mock the DLQ method to prevent actual network calls and allow for assertions
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_transaction_event() -> TransactionEvent:
    """Provides a standard transaction event for testing."""
    return TransactionEvent(
        transaction_id="TXN_POS_CALC_02",
        portfolio_id="PORT_POS_CALC_01",
        instrument_id="INST_POS_CALC_01",
        security_id="SEC_POS_CALC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="SELL",
        quantity=Decimal("40"),
        price=Decimal("90"),
        gross_transaction_amount=Decimal("3600"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("-3600"),
        net_cost_local=Decimal("-3600"),
        epoch=None,  # Default to an original event
    )


@pytest.fixture
def mock_kafka_message(mock_transaction_event: TransactionEvent) -> MagicMock:
    """Creates a mock Kafka message from a transaction event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_transaction_event.model_dump_json().encode("utf-8")
    mock_msg.key.return_value = mock_transaction_event.portfolio_id.encode("utf-8")
    mock_msg.topic.return_value = "processed_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 123
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = [("correlation_id", b"test-corr-id")]
    return mock_msg


@pytest.fixture
def mock_dependencies():
    """Mocks all external dependencies for the consumer."""
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_db_session.begin.return_value.__aenter__.return_value = AsyncMock()

    get_session_gen = make_single_session_getter(mock_db_session)

    with (
        patch(
            "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionCalculator.calculate",
            new_callable=AsyncMock,
        ) as mock_calculate,
        patch(
            "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.IdempotencyRepository"
        ) as mock_idempotency_class,
        patch(
            "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository"
        ) as mock_position_repo_class,
        patch(
            "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionStateRepository"
        ) as mock_state_repo_class,
    ):
        mock_idempotency_instance = AsyncMock(spec=IdempotencyRepository)
        mock_position_repo_instance = AsyncMock(spec=PositionRepository)
        mock_state_repo_instance = AsyncMock(spec=PositionStateRepository)

        mock_idempotency_class.return_value = mock_idempotency_instance
        mock_position_repo_class.return_value = mock_position_repo_instance
        mock_state_repo_class.return_value = mock_state_repo_instance

        yield {
            "calculate_logic": mock_calculate,
            "idempotency_repo": mock_idempotency_instance,
            "position_repo": mock_position_repo_instance,
            "position_state_repo": mock_state_repo_instance,
        }


async def test_consumer_calls_logic_with_original_event(
    position_consumer: TransactionEventConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    """Tests that an original event (no epoch in payload) calls the logic, and the event object passed has epoch=None."""  # noqa: E501
    # ARRANGE
    mock_dependencies["idempotency_repo"].is_event_processed.return_value = False

    # ACT
    await position_consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_dependencies["calculate_logic"].assert_awaited_once()
    call_kwargs = mock_dependencies["calculate_logic"].call_args.kwargs
    passed_event: TransactionEvent = call_kwargs["event"]
    assert passed_event.epoch is None


async def test_consumer_passes_epoch_from_payload_to_logic(
    position_consumer: TransactionEventConsumer,
    mock_kafka_message: MagicMock,
    mock_transaction_event: TransactionEvent,
    mock_dependencies: dict,
):
    """Tests that the consumer correctly parses the epoch from the payload and passes it to the logic layer inside the event object."""  # noqa: E501
    # ARRANGE
    mock_dependencies["idempotency_repo"].is_event_processed.return_value = False
    mock_transaction_event.epoch = 2
    mock_kafka_message.value.return_value = mock_transaction_event.model_dump_json().encode("utf-8")

    # ACT
    await position_consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_dependencies["calculate_logic"].assert_awaited_once()
    call_kwargs = mock_dependencies["calculate_logic"].call_args.kwargs
    passed_event: TransactionEvent = call_kwargs["event"]
    assert passed_event.epoch == 2


async def test_consumer_skips_already_processed_events(
    position_consumer: TransactionEventConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    """Tests that if the idempotency check returns True, the business logic is not called."""
    # ARRANGE
    mock_dependencies["idempotency_repo"].is_event_processed.return_value = True

    # ACT
    await position_consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_dependencies["idempotency_repo"].is_event_processed.assert_awaited_once()
    mock_dependencies["calculate_logic"].assert_not_awaited()


# --- NEW TEST ---
async def test_consumer_sends_to_dlq_on_logic_failure(
    position_consumer: TransactionEventConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    """
    GIVEN an event that causes an unexpected error in the logic layer
    WHEN the consumer processes the message
    THEN it should send the message to the DLQ and not call other repos.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_calculate_logic = mock_dependencies["calculate_logic"]

    mock_idempotency_repo.is_event_processed.return_value = False

    # Simulate a crash inside the core business logic
    processing_error = Exception("Unexpected database constraint violation!")
    mock_calculate_logic.side_effect = processing_error

    # ACT
    await position_consumer.process_message(mock_kafka_message)

    # ASSERT
    # 1. Verify it attempted to process the message
    mock_calculate_logic.assert_awaited_once()

    # 2. Verify it sent the message to the DLQ
    position_consumer._send_to_dlq_async.assert_awaited_once_with(
        mock_kafka_message, processing_error
    )

    # 3. Verify it did NOT try to mark the event as processed, as it failed
    mock_idempotency_repo.mark_event_processed.assert_not_called()
