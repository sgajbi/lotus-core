# tests/unit/services/persistence_service/consumers/test_persistence_market_price_consumer.py
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.config import KAFKA_MARKET_PRICE_PERSISTED_TOPIC
from portfolio_common.database_models import MarketPrice as DBMarketPrice
from portfolio_common.events import MarketPriceEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.consumers.market_price_consumer import MarketPriceConsumer
from src.services.persistence_service.app.repositories.market_price_repository import (
    MarketPriceRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def market_price_consumer():
    """Provides an instance of the consumer for testing."""
    return MarketPriceConsumer(
        bootstrap_servers="mock_server",
        topic="market_prices",
        group_id="test_group",
        dlq_topic="persistence.dlq",
    )


@pytest.fixture
def valid_market_price_event():
    """Provides a valid MarketPriceEvent object."""
    return MarketPriceEvent(
        security_id="SEC_TEST_PRICE",
        price_date=date(2025, 7, 31),
        price=Decimal("125.50"),
        currency="USD",
    )


@pytest.fixture
def mock_kafka_message(valid_market_price_event: MarketPriceEvent):
    """Creates a mock Kafka message containing a valid market price."""
    mock_message = MagicMock()
    mock_message.value.return_value = valid_market_price_event.model_dump_json().encode("utf-8")
    mock_message.key.return_value = valid_market_price_event.security_id.encode("utf-8")
    mock_message.error.return_value = None
    mock_message.topic.return_value = "market_prices"
    mock_message.partition.return_value = 0
    mock_message.offset.return_value = 1
    mock_message.headers.return_value = [("correlation_id", b"test-corr-id")]
    return mock_message


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_repo = AsyncMock(spec=MarketPriceRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    # FIX: The `begin()` method must return an async context manager.
    # An AsyncMock can be used as one directly.
    mock_db_session.begin.return_value = AsyncMock()

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.persistence_service.app.consumers.market_price_consumer.MarketPriceRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
    ):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
            "outbox_repo": mock_outbox_repo,
        }


async def test_process_message_success(
    market_price_consumer: MarketPriceConsumer,
    mock_kafka_message: MagicMock,
    valid_market_price_event: MarketPriceEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a valid market price message
    WHEN the process_message method is called
    THEN it should save the price and create an outbox event.
    """
    # Arrange
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False

    # Simulate the repository returning a persisted DB model instance
    persisted_price = DBMarketPrice(**valid_market_price_event.model_dump())
    mock_repo.create_market_price.return_value = persisted_price

    # Use patch.object for robust mocking
    with patch.object(
        market_price_consumer, "_send_to_dlq_async", new_callable=AsyncMock
    ) as mock_send_to_dlq:
        # Act
        await market_price_consumer.process_message(mock_kafka_message)

        # Assert
        mock_repo.create_market_price.assert_called_once_with(valid_market_price_event)

        # Assert an outbox event was created for the correct topic
        mock_outbox_repo.create_outbox_event.assert_called_once()
        call_args = mock_outbox_repo.create_outbox_event.call_args.kwargs
        assert call_args["topic"] == KAFKA_MARKET_PRICE_PERSISTED_TOPIC
        assert call_args["aggregate_id"] == valid_market_price_event.security_id
        assert call_args["payload"]["security_id"] == valid_market_price_event.security_id

        mock_idempotency_repo.mark_event_processed.assert_called_once()
        mock_send_to_dlq.assert_not_called()
