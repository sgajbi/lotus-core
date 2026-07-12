# tests/unit/libs/portfolio-common/test_idempotency_repository.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.idempotency_repository import (
    IdempotencyRepository,
    SemanticEventClaimOutcome,
)

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
    assert params["correlation_missing_reason"] == "correlation_id_not_supplied"
    assert (
        params["alternate_lookup_key"]
        == "processed_event|event_id=evt-1|portfolio_id=P1|service_name=svc"
    )


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


@pytest.mark.parametrize(
    ("existing_row", "expected"),
    [
        (
            ("topic-0-42", None, None),
            SemanticEventClaimOutcome.PHYSICAL_DUPLICATE,
        ),
        (
            ("topic-0-42", "transaction:v1:P1:T1:0", "sha256:same"),
            SemanticEventClaimOutcome.PHYSICAL_DUPLICATE,
        ),
        (
            ("other-topic-2-7", "transaction:v1:P1:T1:0", "sha256:same"),
            SemanticEventClaimOutcome.SEMANTIC_DUPLICATE,
        ),
        (
            ("other-topic-2-7", "transaction:v1:P1:T1:0", "sha256:different"),
            SemanticEventClaimOutcome.SEMANTIC_CONFLICT,
        ),
    ],
)
async def test_semantic_claim_classifies_existing_fence(
    repository: IdempotencyRepository,
    mock_db_session: AsyncMock,
    existing_row: tuple[str, str | None, str | None],
    expected: SemanticEventClaimOutcome,
) -> None:
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    select_result = MagicMock()
    select_result.all.return_value = [existing_row]
    mock_db_session.execute.side_effect = [insert_result, select_result]

    outcome = await repository.claim_semantic_event_processing(
        event_id="topic-0-42",
        portfolio_id="P1",
        service_name="transaction-processing",
        semantic_key="transaction:v1:P1:T1:0",
        payload_fingerprint="sha256:same",
        correlation_id="corr-1",
    )

    assert outcome is expected


async def test_semantic_claim_returns_claimed_for_new_fence(
    repository: IdempotencyRepository,
    mock_db_session: AsyncMock,
) -> None:
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = 81
    mock_db_session.execute.return_value = insert_result

    outcome = await repository.claim_semantic_event_processing(
        event_id="topic-0-42",
        portfolio_id="P1",
        service_name="transaction-processing",
        semantic_key="transaction:v1:P1:T1:0",
        payload_fingerprint="sha256:same",
        correlation_id="corr-1",
    )

    assert outcome is SemanticEventClaimOutcome.CLAIMED
    stmt = mock_db_session.execute.await_args.args[0]
    params = stmt.compile().params
    assert params["semantic_key"] == "transaction:v1:P1:T1:0"
    assert params["payload_fingerprint"] == "sha256:same"


async def test_semantic_claim_fails_closed_when_conflict_row_is_not_visible(
    repository: IdempotencyRepository,
    mock_db_session: AsyncMock,
) -> None:
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    select_result = MagicMock()
    select_result.all.return_value = []
    mock_db_session.execute.side_effect = [insert_result, select_result]

    with pytest.raises(RuntimeError, match="without a matching durable fence"):
        await repository.claim_semantic_event_processing(
            event_id="topic-0-42",
            portfolio_id="P1",
            service_name="transaction-processing",
            semantic_key="transaction:v1:P1:T1:0",
            payload_fingerprint="sha256:same",
        )
