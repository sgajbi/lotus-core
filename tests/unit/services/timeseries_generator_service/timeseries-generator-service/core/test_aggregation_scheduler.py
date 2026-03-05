# tests/unit/services/timeseries-generator-service/core/test_aggregation_scheduler.py
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.config import KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.kafka_utils import KafkaProducer
from sqlalchemy.ext.asyncio import AsyncSession

from services.timeseries_generator_service.app.core.aggregation_scheduler import (
    AggregationScheduler,
)
from src.services.timeseries_generator_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    return MagicMock(spec=KafkaProducer)


@pytest.fixture
def scheduler(mock_kafka_producer: MagicMock) -> AggregationScheduler:
    """Provides an AggregationScheduler instance with a mocked producer."""
    with patch(
        "services.timeseries_generator_service.app.core.aggregation_scheduler.get_kafka_producer",
        return_value=mock_kafka_producer,
    ):
        yield AggregationScheduler(
            poll_interval=0.01
        )  # Use a tiny interval for fast test execution


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the scheduler test."""
    mock_repo = AsyncMock(spec=TimeseriesRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "services.timeseries_generator_service.app.core.aggregation_scheduler.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "services.timeseries_generator_service.app.core.aggregation_scheduler.TimeseriesRepository",
            return_value=mock_repo,
        ),
    ):
        yield {"repo": mock_repo}


async def test_scheduler_run_cycle(
    scheduler: AggregationScheduler, mock_kafka_producer: MagicMock, mock_dependencies: dict
):
    """
    GIVEN a set of pending jobs in the database
    WHEN the scheduler's main run loop executes for one cycle
    THEN it should find and reset stale jobs, claim eligible jobs, and dispatch them to Kafka.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    claimed_jobs = [
        PortfolioAggregationJob(
            id=1,
            portfolio_id="PORT_01",
            aggregation_date=date(2025, 8, 10),
            correlation_id="corr-1",
        ),
        PortfolioAggregationJob(
            id=2,
            portfolio_id="PORT_02",
            aggregation_date=date(2025, 8, 11),
            correlation_id="corr-2",
        ),
    ]

    # This side effect ensures the scheduler's loop runs exactly once for our test.
    async def find_and_stop(*args, **kwargs):
        scheduler.stop()  # Signal the scheduler to stop its loop after this logic
        return claimed_jobs

    mock_repo.find_and_claim_eligible_jobs.side_effect = find_and_stop

    # ACT
    # Run the scheduler task to completion. It will stop itself after one cycle.
    await scheduler.run()

    # ASSERT
    mock_repo.find_and_reset_stale_jobs.assert_called_once()
    mock_repo.find_and_claim_eligible_jobs.assert_called_once()

    assert mock_kafka_producer.publish_message.call_count == 2
    mock_kafka_producer.flush.assert_called_once()

    first_call_args = mock_kafka_producer.publish_message.call_args_list[0].kwargs
    assert first_call_args["topic"] == KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC
    assert first_call_args["key"] == "PORT_01"
    assert first_call_args["value"]["portfolio_id"] == "PORT_01"
    assert first_call_args["value"]["aggregation_date"] == "2025-08-10"
    assert "security_id" not in first_call_args["value"]
