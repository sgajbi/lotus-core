# tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)
from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture
def transaction_consumer():
    """Provides an instance of the consumer for testing."""
    return TransactionPersistenceConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.raw.received",
        group_id="test_group",
        dlq_topic="dlq.persistence_service",
    )


@pytest.fixture
def valid_transaction_event():
    """Provides a valid TransactionEvent object."""
    return TransactionEvent(
        transaction_id="UNIT_TEST_01",
        portfolio_id="PORT_UT_01",
        instrument_id="INST_UT_01",
        security_id="SEC_UT_01",
        transaction_date="2025-07-31T12:00:00",
        transaction_type="BUY",
        quantity=100,
        price=50,
        gross_transaction_amount=5000,
        trade_currency="USD",
        currency="USD",
    )


@pytest.fixture
def mock_kafka_message(valid_transaction_event: TransactionEvent):
    """Creates a mock Kafka message containing a valid transaction."""
    mock_message = MagicMock()
    mock_message.value.return_value = valid_transaction_event.model_dump_json().encode("utf-8")
    mock_message.key.return_value = "test_key".encode("utf-8")
    mock_message.error.return_value = None
    mock_message.topic.return_value = "transactions.raw.received"
    mock_message.partition.return_value = 0
    mock_message.offset.return_value = 1
    mock_message.headers.return_value = [("correlation_id", b"test-corr-id")]
    return mock_message


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_repo = AsyncMock(spec=TransactionDBRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)

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
            "src.services.persistence_service.app.consumers.transaction_consumer.TransactionDBRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
        patch(
            "src.services.persistence_service.app.consumers.base_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
    ):
        yield {
            "repo": mock_repo,
            "outbox_repo": mock_outbox_repo,
            "idempotency_repo": mock_idempotency_repo,
        }


async def test_process_message_success(
    transaction_consumer: TransactionPersistenceConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    """
    GIVEN a valid transaction message
    WHEN the process_message method is called
    THEN it should call the repository to save the transaction
    AND publish a completion event.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_repo.check_portfolio_exists.return_value = True
    mock_idempotency_repo.is_event_processed.return_value = False

    # Use patch.object for robust mocking
    with patch.object(
        transaction_consumer, "_send_to_dlq_async", new_callable=AsyncMock
    ) as mock_send_to_dlq:
        # ACT
        await transaction_consumer.process_message(mock_kafka_message)

        # ASSERT
        mock_repo.create_or_update_transaction.assert_called_once()
        mock_outbox_repo.create_outbox_event.assert_called_once()
        assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
            "test-corr-id"
        )
        mock_idempotency_repo.mark_event_processed.assert_awaited_once_with(
            event_id="UNIT_TEST_01",
            portfolio_id="PORT_UT_01",
            service_name="persistence-transactions",
            correlation_id="test-corr-id",
        )
        mock_send_to_dlq.assert_not_called()


async def test_process_message_uses_header_correlation_on_direct_path(
    transaction_consumer: TransactionPersistenceConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_repo.check_portfolio_exists.return_value = True
    mock_idempotency_repo.is_event_processed.return_value = False

    token = correlation_id_var.set("<not-set>")
    try:
        await transaction_consumer.process_message(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
        "test-corr-id"
    )
    mock_idempotency_repo.mark_event_processed.assert_awaited_once_with(
        event_id="UNIT_TEST_01",
        portfolio_id="PORT_UT_01",
        service_name="persistence-transactions",
        correlation_id="test-corr-id",
    )


# --- REVISED TEST ---
async def test_handle_persistence_retries_and_succeeds(
    transaction_consumer: TransactionPersistenceConsumer,
    valid_transaction_event: TransactionEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a transaction for a portfolio that initially does not exist
    WHEN handle_persistence is called
    THEN it should retry and succeed once the portfolio exists.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]

    # Simulate portfolio not found on first call, but found on the second
    mock_repo.check_portfolio_exists.side_effect = [False, True]

    # ACT
    # This call will invoke the retry logic internally and should complete without error
    await transaction_consumer.handle_persistence(AsyncMock(), valid_transaction_event)

    # ASSERT
    # Verify the check was called twice (initial attempt + 1 retry)
    assert mock_repo.check_portfolio_exists.call_count == 2

    # Verify the transaction was created only on the successful attempt
    mock_repo.create_or_update_transaction.assert_awaited_once_with(valid_transaction_event)
