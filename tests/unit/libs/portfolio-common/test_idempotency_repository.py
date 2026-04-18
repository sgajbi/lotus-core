# tests/unit/libs/portfolio-common/test_idempotency_repository.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.idempotency_repository import IdempotencyRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
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


async def test_mark_event_processed_inserts_processed_event_fence(
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

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = 11
    mock_db_session.execute.return_value = execute_result

    await repository.mark_event_processed(event_id, portfolio_id, service_name, correlation_id)

    stmt = mock_db_session.execute.await_args.args[0]
    stmt_text = str(stmt)

    assert "INSERT INTO processed_events" in stmt_text
    assert "ON CONFLICT (event_id, service_name) DO NOTHING" in stmt_text
    assert "RETURNING processed_events.id" in stmt_text


async def test_mark_event_processed_normalizes_sentinel_correlation(
    repository: IdempotencyRepository, mock_db_session: AsyncMock
):
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = 12
    mock_db_session.execute.return_value = execute_result

    await repository.mark_event_processed("evt-1", "P1", "svc", "<not-set>")

    stmt = mock_db_session.execute.await_args.args[0]
    params = stmt.compile().params
    assert params["correlation_id"] is None


async def test_claim_event_processing_returns_true_for_new_fence(
    repository: IdempotencyRepository, mock_db_session: AsyncMock
):
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = 7
    mock_db_session.execute.return_value = execute_result

    claimed = await repository.claim_event_processing("evt-2", "P1", "svc", "corr-2")

    assert claimed is True


async def test_claim_event_processing_returns_false_when_fence_exists(
    repository: IdempotencyRepository, mock_db_session: AsyncMock
):
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = execute_result

    claimed = await repository.claim_event_processing("evt-2", "P1", "svc", "corr-2")

    assert claimed is False
