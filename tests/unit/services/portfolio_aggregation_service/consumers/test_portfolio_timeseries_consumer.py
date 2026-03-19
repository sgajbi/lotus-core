# tests/unit/services/portfolio_aggregation_service/consumers/test_portfolio_timeseries_consumer.py
import logging
from datetime import date
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    Portfolio,
)
from portfolio_common.events import PortfolioAggregationRequiredEvent
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_aggregation_service.app.consumers.portfolio_timeseries_consumer import (
    PortfolioTimeseriesConsumer,
)
from src.services.portfolio_aggregation_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)
from tests.unit.test_support.async_session_iter import make_single_session_getter

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer() -> PortfolioTimeseriesConsumer:
    """Provides a clean instance of the PortfolioTimeseriesConsumer."""
    consumer = PortfolioTimeseriesConsumer(
        bootstrap_servers="mock_server",
        topic="portfolio_day.aggregation.job.requested",
        group_id="test_group",
        dlq_topic="test.dlq",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_event() -> PortfolioAggregationRequiredEvent:
    """Provides a consistent aggregation event for tests."""
    return PortfolioAggregationRequiredEvent(
        portfolio_id="PORT_AGG_01", aggregation_date=date(2025, 8, 11)
    )


@pytest.fixture
def mock_kafka_message(mock_event: PortfolioAggregationRequiredEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    mock_msg.key.return_value = "test_key".encode("utf-8")
    mock_msg.headers.return_value = [("correlation_id", b"test-corr-id")]
    return mock_msg


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the consumer test."""
    mock_repo = AsyncMock(spec=TimeseriesRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction

    get_session_gen = make_single_session_getter(mock_db_session)

    mock_repo_class = MagicMock(return_value=mock_repo)

    with (
        patch(
            "src.services.portfolio_aggregation_service.app.consumers.portfolio_timeseries_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.portfolio_aggregation_service.app.consumers.portfolio_timeseries_consumer.TimeseriesRepository",
            new=mock_repo_class,
        ),
        patch(
            "src.services.portfolio_aggregation_service.app.consumers.portfolio_timeseries_consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
        patch(
            "src.services.portfolio_aggregation_service.app.consumers.portfolio_timeseries_consumer.PortfolioTimeseriesLogic.calculate_daily_record"
        ) as mock_logic,
    ):
        yield {
            "repo": mock_repo,
            "db_session": mock_db_session,
            "logic": mock_logic,
            "outbox_repo": mock_outbox_repo,
        }


async def test_process_message_success(
    consumer: PortfolioTimeseriesConsumer,
    mock_event: PortfolioAggregationRequiredEvent,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    """
    GIVEN a portfolio aggregation event
    WHEN the message is processed successfully
    THEN it should fetch the current epoch and pass it to the logic layer.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_logic = mock_dependencies["logic"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_repo.get_portfolio.return_value = Portfolio(
        portfolio_id=mock_event.portfolio_id, base_currency="USD"
    )
    mock_repo.get_current_epoch_for_portfolio.return_value = 2  # Simulate current epoch is 2
    mock_repo.get_all_position_timeseries_for_date.return_value = []

    with patch.object(consumer, "_update_job_status", new_callable=AsyncMock) as mock_update_status:
        # ACT
        await consumer.process_message(mock_kafka_message)

        # ASSERT
        mock_repo.get_current_epoch_for_portfolio.assert_called_once_with(mock_event.portfolio_id)
        mock_repo.get_all_position_timeseries_for_date.assert_called_once_with(
            mock_event.portfolio_id,
            mock_event.aggregation_date,
            2,  # Assert it uses the fetched epoch
        )
        mock_logic.assert_awaited_once()
        assert mock_logic.call_args.kwargs["epoch"] == 2
        mock_repo.upsert_portfolio_timeseries.assert_called_once()
        mock_update_status.assert_called_once_with(
            mock_event.portfolio_id, mock_event.aggregation_date, "COMPLETE", db_session=ANY
        )
        mock_outbox_repo.create_outbox_event.assert_awaited_once()
        assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
            "test-corr-id"
        )


async def test_process_message_uses_header_correlation_on_direct_path(
    consumer: PortfolioTimeseriesConsumer,
    mock_event: PortfolioAggregationRequiredEvent,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_logic = mock_dependencies["logic"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_repo.get_portfolio.return_value = Portfolio(
        portfolio_id=mock_event.portfolio_id, base_currency="USD"
    )
    mock_repo.get_current_epoch_for_portfolio.return_value = 2
    mock_repo.get_all_position_timeseries_for_date.return_value = []

    token = correlation_id_var.set("<not-set>")
    try:
        with patch.object(consumer, "_update_job_status", new_callable=AsyncMock):
            await consumer.process_message(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    mock_logic.assert_awaited_once()
    assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
        "test-corr-id"
    )


async def test_process_message_skips_completion_side_effects_when_job_ownership_is_lost(
    consumer: PortfolioTimeseriesConsumer,
    mock_event: PortfolioAggregationRequiredEvent,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_logic = mock_dependencies["logic"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_repo.get_portfolio.return_value = Portfolio(
        portfolio_id=mock_event.portfolio_id, base_currency="USD"
    )
    mock_repo.get_current_epoch_for_portfolio.return_value = 2
    mock_repo.get_all_position_timeseries_for_date.return_value = []

    with patch.object(
        consumer,
        "_update_job_status",
        new=AsyncMock(return_value=False),
    ) as mock_update_status:
        await consumer.process_message(mock_kafka_message)

    mock_logic.assert_awaited_once()
    mock_update_status.assert_awaited_once_with(
        mock_event.portfolio_id,
        mock_event.aggregation_date,
        "COMPLETE",
        db_session=ANY,
    )
    mock_repo.upsert_portfolio_timeseries.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()
