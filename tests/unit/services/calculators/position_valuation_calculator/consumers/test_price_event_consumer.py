# tests/unit/services/calculators/position-valuation-calculator/consumers/test_price_event_consumer.py  # noqa: E501
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import MarketPricePersistedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy.ext.asyncio import AsyncSession

from services.calculators.position_valuation_calculator.app.consumers.price_event_consumer import (
    PriceEventConsumer,
)
from services.calculators.position_valuation_calculator.app.repositories.instrument_reprocessing_state_repository import (  # noqa: E501
    InstrumentReprocessingStateRepository,
)
from services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer() -> PriceEventConsumer:
    """Provides a clean instance of the PriceEventConsumer."""
    consumer = PriceEventConsumer(
        bootstrap_servers="mock_server",
        topic="market_price_persisted",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_event() -> MarketPricePersistedEvent:
    """Provides a consistent market price event for tests."""
    return MarketPricePersistedEvent(
        security_id="SEC_TEST_PRICE_EVENT", price_date=date(2025, 8, 5), price=150.0, currency="USD"
    )


@pytest.fixture
def mock_kafka_message(mock_event: MarketPricePersistedEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    mock_msg.key.return_value = mock_event.security_id.encode("utf-8")
    mock_msg.topic.return_value = "market_price_persisted"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.headers.return_value = []
    return mock_msg


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the consumer test."""
    mock_valuation_repo = AsyncMock(spec=ValuationRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_reprocessing_repo = AsyncMock(spec=InstrumentReprocessingStateRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.ValuationRepository",
            return_value=mock_valuation_repo,
        ),
        patch(
            "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.InstrumentReprocessingStateRepository",
            return_value=mock_reprocessing_repo,
        ),
    ):
        yield {
            "valuation_repo": mock_valuation_repo,
            "idempotency_repo": mock_idempotency_repo,
            "reprocessing_repo": mock_reprocessing_repo,
        }


async def test_backdated_price_flags_instrument_for_reprocessing(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a back-dated market price event
    WHEN the message is processed
    THEN it should flag the instrument by calling the reprocessing state repository.
    """
    # ARRANGE
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_reprocessing_repo = mock_dependencies["reprocessing_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    # Simulate a back-dated event
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date + timedelta(
        days=5
    )

    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_reprocessing_repo.upsert_state.assert_awaited_once_with(
        security_id=mock_event.security_id, price_date=mock_event.price_date
    )
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()


async def test_current_price_does_not_flag_instrument(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a current-day market price event
    WHEN the message is processed
    THEN it should NOT flag the instrument for reprocessing.
    """
    # ARRANGE
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_reprocessing_repo = mock_dependencies["reprocessing_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    # Simulate a current event
    mock_valuation_repo.get_latest_business_date.return_value = mock_event.price_date

    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_reprocessing_repo.upsert_state.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()
