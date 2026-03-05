# tests/unit/libs/portfolio-common/test_idempotency_repository.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import ProcessedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    # FIX: Configure .add() as a synchronous MagicMock on the async mock instance
    session.add = MagicMock()
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> IdempotencyRepository:
    """Provides an instance of the IdempotencyRepository with a mock session."""
    return IdempotencyRepository(mock_db_session)


async def test_is_event_processed_returns_true_when_exists(
    repository: IdempotencyRepository, mock_db_session: AsyncMock
):
    """
    GIVEN an event ID that exists in the database
    WHEN is_event_processed is called
    THEN it should return True.
    """
    # Arrange
    mock_result = MagicMock()
    mock_result.scalar.return_value = True
    mock_db_session.execute.return_value = mock_result

    event_id = "test-event-1"
    service_name = "test-service"

    # Act
    is_processed = await repository.is_event_processed(event_id, service_name)

    # Assert
    assert is_processed is True
    mock_db_session.execute.assert_called_once()


async def test_is_event_processed_returns_false_when_not_exists(
    repository: IdempotencyRepository, mock_db_session: AsyncMock
):
    """
    GIVEN an event ID that does not exist in the database
    WHEN is_event_processed is called
    THEN it should return False.
    """
    # Arrange
    mock_result = MagicMock()
    mock_result.scalar.return_value = False
    mock_db_session.execute.return_value = mock_result

    event_id = "test-event-2"
    service_name = "test-service"

    # Act
    is_processed = await repository.is_event_processed(event_id, service_name)

    # Assert
    assert is_processed is False
    mock_db_session.execute.assert_called_once()


async def test_mark_event_processed_adds_to_session(
    repository: IdempotencyRepository, mock_db_session: AsyncMock
):
    """
    GIVEN event details
    WHEN mark_event_processed is called
    THEN it should add the correct ProcessedEvent object to the session.
    """
    # Arrange
    event_id = "test-event-3"
    portfolio_id = "port-1"
    service_name = "test-service"
    correlation_id = "corr-id-123"

    # Act
    await repository.mark_event_processed(event_id, portfolio_id, service_name, correlation_id)

    # Assert
    mock_db_session.add.assert_called_once()
    added_object = mock_db_session.add.call_args[0][0]

    assert isinstance(added_object, ProcessedEvent)
    assert added_object.event_id == event_id
    assert added_object.portfolio_id == portfolio_id
    assert added_object.service_name == service_name
    assert added_object.correlation_id == correlation_id
