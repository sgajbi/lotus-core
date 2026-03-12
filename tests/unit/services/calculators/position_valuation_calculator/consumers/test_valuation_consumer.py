# tests/unit/services/calculators/position-valuation-calculator/consumers/test_valuation_consumer.py
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    Portfolio,
    PositionHistory,
)
from portfolio_common.events import (
    PortfolioValuationRequiredEvent,
)
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from services.calculators.position_valuation_calculator.app.consumers.valuation_consumer import (
    ValuationConsumer,
)
from services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)
from tests.unit.test_support.async_session_iter import make_single_session_getter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer() -> ValuationConsumer:
    """Provides a clean instance of the ValuationConsumer."""
    consumer = ValuationConsumer(
        bootstrap_servers="mock_server",
        topic="valuation_required",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_event() -> PortfolioValuationRequiredEvent:
    """Provides a consistent valuation event for tests."""
    return PortfolioValuationRequiredEvent(
        portfolio_id="PORT_VAL_01",
        security_id="SEC_VAL_01",
        valuation_date=date(2025, 8, 1),
        epoch=1,
    )


@pytest.fixture
def mock_kafka_message(mock_event: PortfolioValuationRequiredEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    mock_msg.key.return_value = mock_event.portfolio_id.encode("utf-8")
    mock_msg.topic.return_value = "valuation_required"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = [("correlation_id", b"test-corr-id-123")]
    return mock_msg


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    mock_valuation_repo = AsyncMock(spec=ValuationRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_begin_transaction():
        yield

    mock_db_session.begin.side_effect = mock_begin_transaction

    get_session_gen = make_single_session_getter(mock_db_session)

    with (
        patch(
            "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.ValuationRepository",
            return_value=mock_valuation_repo,
        ),
        patch(
            "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
    ):
        yield {
            "idempotency_repo": mock_idempotency_repo,
            "outbox_repo": mock_outbox_repo,
            "valuation_repo": mock_valuation_repo,
        }


async def test_valuation_consumer_success(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a valid valuation required event with an epoch
    WHEN the consumer processes the message
    THEN it should fetch position history for that epoch and create an
    epoch-tagged snapshot and event.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False

    mock_position_history = PositionHistory(
        quantity=Decimal("100"), cost_basis=Decimal("10000"), cost_basis_local=Decimal("8000")
    )
    mock_valuation_repo.get_last_position_history_before_date.return_value = mock_position_history

    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="EUR", security_id=mock_event.security_id
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD", portfolio_id=mock_event.portfolio_id
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"), currency="EUR", price_date=mock_event.valuation_date
    )
    mock_valuation_repo.get_fx_rate.return_value = FxRate(rate=Decimal("1.1"))

    persisted_snapshot = DailyPositionSnapshot(
        id=1,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.valuation_date,
        epoch=mock_event.epoch,
    )
    mock_valuation_repo.upsert_daily_snapshot.return_value = persisted_snapshot

    token = correlation_id_var.set("<not-set>")
    try:
        # ACT
        await consumer.process_message(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    # ASSERT
    mock_valuation_repo.get_last_position_history_before_date.assert_called_once_with(
        mock_event.portfolio_id, mock_event.security_id, mock_event.valuation_date, mock_event.epoch
    )
    assert mock_outbox_repo.create_outbox_event.call_count == 2

    first_payload = mock_outbox_repo.create_outbox_event.call_args_list[0].kwargs["payload"]
    second_payload = mock_outbox_repo.create_outbox_event.call_args_list[1].kwargs["payload"]
    assert first_payload["epoch"] == mock_event.epoch
    assert second_payload["epoch"] == mock_event.epoch
    assert second_payload["daily_position_snapshot_id"] == persisted_snapshot.id
    assert mock_outbox_repo.create_outbox_event.call_args_list[0].kwargs["correlation_id"] == (
        "test-corr-id-123"
    )
    assert mock_idempotency_repo.mark_event_processed.call_args.args[3] == "test-corr-id-123"


async def test_process_message_handles_data_not_found_error(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a job for which no position history exists
    WHEN the consumer processes the message
    THEN it should catch DataNotFoundError, mark the job as SKIPPED, and NOT send to DLQ.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False

    # Simulate the key error condition by having the repo return None
    mock_valuation_repo.get_last_position_history_before_date.return_value = None

    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    # Verify the job status was updated to the terminal 'SKIPPED' state
    mock_valuation_repo.update_job_status.assert_called_once()
    call_args = mock_valuation_repo.update_job_status.call_args.kwargs
    assert call_args["status"] == "SKIPPED_NO_POSITION"
    assert "Position history not found" in call_args["failure_reason"]

    # Verify other actions were NOT taken
    mock_outbox_repo.create_outbox_event.assert_not_called()
    consumer._send_to_dlq_async.assert_not_called()

    # Verify the event was still marked as processed to prevent retries
    mock_idempotency_repo.mark_event_processed.assert_called_once()


async def test_process_message_handles_unexpected_error(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    """
    GIVEN a valid job that causes an unexpected error during valuation
    WHEN the consumer processes the message
    THEN it should mark the job as FAILED and send the message to the DLQ.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False

    # Mock all repo calls to succeed up to the point of failure
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=1, cost_basis=1
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(currency="USD")
    mock_valuation_repo.get_portfolio.return_value = Portfolio(base_currency="USD")

    # ACT
    # Patch the logic layer to raise an unexpected error
    with patch(
        "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.ValuationLogic.calculate_valuation",
        side_effect=ValueError("Unexpected logic error"),
    ) as mock_logic:
        await consumer.process_message(mock_kafka_message)

    # ASSERT
    # Verify the logic was called, triggering the error
    mock_logic.assert_called_once()

    # Verify the job status was updated to FAILED
    mock_valuation_repo.update_job_status.assert_called_once()
    call_args = mock_valuation_repo.update_job_status.call_args.kwargs
    assert call_args["status"] == "FAILED"
    assert "Unexpected logic error" in call_args["failure_reason"]

    # Verify the message was sent to the DLQ
    consumer._send_to_dlq_async.assert_called_once()

    # Verify no success event was published
    mock_outbox_repo.create_outbox_event.assert_not_called()

    # Idempotency key should NOT be marked as processed, as the message went to DLQ for retry
    mock_idempotency_repo.mark_event_processed.assert_not_called()


async def test_process_message_marks_job_failed_when_fx_rate_missing(
    consumer: ValuationConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioValuationRequiredEvent,
    mock_dependencies: dict,
):
    """
    GIVEN valuation requires cross-currency conversion and FX is missing
    WHEN the consumer processes the message
    THEN it should persist a FAILED valuation snapshot and mark the job FAILED.
    """
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_valuation_repo.get_last_position_history_before_date.return_value = PositionHistory(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("8000"),
    )
    mock_valuation_repo.get_instrument.return_value = Instrument(
        currency="EUR",
        security_id=mock_event.security_id,
    )
    mock_valuation_repo.get_portfolio.return_value = Portfolio(
        base_currency="USD",
        portfolio_id=mock_event.portfolio_id,
    )
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(
        price=Decimal("90"),
        currency="EUR",
        price_date=mock_event.valuation_date,
    )
    mock_valuation_repo.get_fx_rate.return_value = None
    mock_valuation_repo.upsert_daily_snapshot.return_value = DailyPositionSnapshot(
        id=1,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.valuation_date,
        epoch=mock_event.epoch,
        valuation_status="FAILED",
    )

    await consumer.process_message(mock_kafka_message)

    mock_valuation_repo.update_job_status.assert_called_once()
    update_args = mock_valuation_repo.update_job_status.call_args.args
    update_kwargs = mock_valuation_repo.update_job_status.call_args.kwargs
    assert update_args[4] == "FAILED"
    assert "Missing FX rate" in update_kwargs["failure_reason"]
    assert mock_outbox_repo.create_outbox_event.call_count == 2
    consumer._send_to_dlq_async.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_called_once()
