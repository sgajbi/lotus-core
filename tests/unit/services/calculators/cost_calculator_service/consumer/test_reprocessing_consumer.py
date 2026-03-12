# tests/unit/services/calculators/cost_calculator_service/consumer/test_reprocessing_consumer.py
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.reprocessing_repository import ReprocessingRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cost_calculator_service.app.consumers.reprocessing_consumer import (
    ReprocessingConsumer,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer() -> ReprocessingConsumer:
    """Provides a clean instance of the ReprocessingConsumer."""
    consumer = ReprocessingConsumer(
        bootstrap_servers="mock_server",
        topic="transactions_reprocessing_requested",
        group_id="test_reprocessing_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_kafka_message() -> MagicMock:
    """Creates a mock Kafka message for a reprocessing request."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = b'{"transaction_id": "TXN_TO_REPROCESS"}'
    mock_msg.headers.return_value = [("correlation_id", b"corr-reprocess-001")]
    mock_msg.error.return_value = None
    return mock_msg


@patch(
    "src.services.calculators.cost_calculator_service.app.consumers.reprocessing_consumer.get_kafka_producer"
)
@patch(
    "src.services.calculators.cost_calculator_service.app.consumers.reprocessing_consumer.ReprocessingRepository"
)
async def test_reprocessing_consumer_calls_repository(
    MockReprocessingRepo,
    MockGetKafkaProducer,
    consumer: ReprocessingConsumer,
    mock_kafka_message: MagicMock,
):
    """
    GIVEN a valid reprocessing request message
    WHEN the consumer processes it
    THEN it should instantiate and call the ReprocessingRepository with the correct transaction ID.
    """
    # ARRANGE
    mock_repo_instance = AsyncMock(spec=ReprocessingRepository)
    MockReprocessingRepo.return_value = mock_repo_instance

    # Mock the database session dependency
    mock_db_session = AsyncMock(spec=AsyncSession)

    async def get_session_gen():
        yield mock_db_session

    with patch(
        "src.services.calculators.cost_calculator_service.app.consumers.reprocessing_consumer.get_async_db_session",
        new=get_session_gen,
    ):
        # ACT
        await consumer.process_message(mock_kafka_message)

        # ASSERT
        # Verify the repository was instantiated correctly
        MockReprocessingRepo.assert_called_once_with(db=mock_db_session, kafka_producer=ANY)

        # Verify the correct method was called on the repository instance
        mock_repo_instance.reprocess_transactions_by_ids.assert_awaited_once_with(
            ["TXN_TO_REPROCESS"]
        )
        consumer._send_to_dlq_async.assert_not_called()


@patch(
    "src.services.calculators.cost_calculator_service.app.consumers.reprocessing_consumer.get_kafka_producer"
)
@patch(
    "src.services.calculators.cost_calculator_service.app.consumers.reprocessing_consumer.ReprocessingRepository"
)
async def test_reprocessing_consumer_propagates_header_correlation_id(
    MockReprocessingRepo,
    MockGetKafkaProducer,
    consumer: ReprocessingConsumer,
    mock_kafka_message: MagicMock,
):
    """
    GIVEN a direct consumer invocation with a Kafka correlation header
    WHEN the consumer processes the reprocessing request
    THEN the repository executes under that message correlation context.
    """
    mock_repo_instance = AsyncMock(spec=ReprocessingRepository)

    async def assert_correlation(transaction_ids):
        assert transaction_ids == ["TXN_TO_REPROCESS"]
        assert correlation_id_var.get() == "corr-reprocess-001"

    mock_repo_instance.reprocess_transactions_by_ids.side_effect = assert_correlation
    MockReprocessingRepo.return_value = mock_repo_instance

    mock_db_session = AsyncMock(spec=AsyncSession)

    async def get_session_gen():
        yield mock_db_session

    with patch(
        "src.services.calculators.cost_calculator_service.app.consumers.reprocessing_consumer.get_async_db_session",
        new=get_session_gen,
    ):
        await consumer.process_message(mock_kafka_message)

    consumer._send_to_dlq_async.assert_not_called()
