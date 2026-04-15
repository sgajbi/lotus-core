# tests/unit/libs/portfolio-common/test_outbox_repository.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import OutboxEvent
from portfolio_common.events import CashflowCalculatedEvent
from portfolio_common.outbox_repository import EVENT_SCHEMA_VERSION, OutboxRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    # FIX: Configure .add() as a synchronous MagicMock
    session.add = MagicMock()
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> OutboxRepository:
    """Provides an instance of the OutboxRepository with a mock session."""
    return OutboxRepository(mock_db_session)


async def test_create_outbox_event_success(
    repository: OutboxRepository, mock_db_session: AsyncMock
):
    """
    GIVEN valid event details
    WHEN create_outbox_event is called
    THEN it should add a correctly formed OutboxEvent to the session and flush.
    """
    # Arrange
    event_details = {
        "aggregate_type": "Test",
        "aggregate_id": "agg-123",
        "event_type": "TestEvent",
        "payload": {"data": "value"},
        "topic": "test.topic",
        "correlation_id": "corr-123",
    }

    # Act
    await repository.create_outbox_event(**event_details)

    # Assert
    mock_db_session.add.assert_called_once()
    mock_db_session.flush.assert_awaited_once()

    added_object = mock_db_session.add.call_args[0][0]
    assert isinstance(added_object, OutboxEvent)
    assert added_object.aggregate_id == event_details["aggregate_id"]
    assert added_object.topic == event_details["topic"]
    assert added_object.payload == {
        "data": "value",
        "event_type": "TestEvent",
        "schema_version": EVENT_SCHEMA_VERSION,
        "correlation_id": "corr-123",
    }
    assert added_object.status == "PENDING"
    assert event_details["payload"] == {"data": "value"}


async def test_create_outbox_event_raises_type_error_for_bad_payload(repository: OutboxRepository):
    """
    GIVEN a payload that is not a dictionary
    WHEN create_outbox_event is called
    THEN it should raise a TypeError.
    """
    # Arrange
    event_details = {
        "aggregate_type": "Test",
        "aggregate_id": "agg-123",
        "event_type": "TestEvent",
        "payload": "just a string",  # Invalid payload type
        "topic": "test.topic",
    }

    # Act & Assert
    with pytest.raises(TypeError, match="payload must be a dict"):
        await repository.create_outbox_event(**event_details)


async def test_create_outbox_event_normalizes_sentinel_correlation(
    repository: OutboxRepository, mock_db_session: AsyncMock
):
    event = await repository.create_outbox_event(
        aggregate_type="portfolio",
        aggregate_id="P1",
        event_type="evt",
        payload={"x": 1},
        topic="topic-1",
        correlation_id="<not-set>",
    )

    assert event.correlation_id is None
    assert event.payload["correlation_id"] is None


async def test_create_outbox_event_rejects_conflicting_payload_event_type(
    repository: OutboxRepository,
) -> None:
    with pytest.raises(ValueError, match="payload event_type 'OtherEvent'"):
        await repository.create_outbox_event(
            aggregate_type="portfolio",
            aggregate_id="P1",
            event_type="ExpectedEvent",
            payload={"event_type": "OtherEvent"},
            topic="topic-1",
        )


async def test_create_outbox_event_rejects_conflicting_payload_correlation_id(
    repository: OutboxRepository,
) -> None:
    with pytest.raises(ValueError, match="payload correlation_id 'payload-corr'"):
        await repository.create_outbox_event(
            aggregate_type="portfolio",
            aggregate_id="P1",
            event_type="ExpectedEvent",
            payload={"correlation_id": "payload-corr"},
            topic="topic-1",
            correlation_id="outbox-corr",
        )


async def test_enriched_payload_remains_compatible_with_event_models(
    repository: OutboxRepository,
) -> None:
    event = await repository.create_outbox_event(
        aggregate_type="Cashflow",
        aggregate_id="P1",
        event_type="CashflowCalculated",
        payload={
            "cashflow_id": 101,
            "transaction_id": "T1",
            "portfolio_id": "P1",
            "security_id": "S1",
            "cashflow_date": "2026-04-10",
            "amount": "12.34",
            "currency": "USD",
            "classification": "DIVIDEND",
            "timing": "eod",
            "is_position_flow": True,
            "is_portfolio_flow": False,
            "calculation_type": "standard",
        },
        topic="cashflows.calculated",
        correlation_id="corr-123",
    )

    parsed = CashflowCalculatedEvent.model_validate(event.payload)

    assert parsed.transaction_id == "T1"
    assert event.payload["event_type"] == "CashflowCalculated"
    assert event.payload["schema_version"] == EVENT_SCHEMA_VERSION
