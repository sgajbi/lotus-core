# tests/unit/libs/portfolio-common/test_outbox_repository.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import OutboxEvent
from portfolio_common.outbox_repository import OutboxRepository

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
    assert added_object.payload == event_details["payload"]
    assert added_object.status == "PENDING"


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
