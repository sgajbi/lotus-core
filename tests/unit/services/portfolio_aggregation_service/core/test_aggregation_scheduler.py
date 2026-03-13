from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from portfolio_common.config import KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.kafka_utils import KafkaProducer

from src.services.portfolio_aggregation_service.app.core.aggregation_scheduler import (
    AggregationScheduler,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    return MagicMock(spec=KafkaProducer)


@pytest.fixture
def scheduler(mock_kafka_producer: MagicMock) -> AggregationScheduler:
    with patch(
        "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.get_kafka_producer",
        return_value=mock_kafka_producer,
    ):
        return AggregationScheduler()


async def test_scheduler_dispatches_claimed_jobs_with_correlation_header(
    scheduler: AggregationScheduler,
    mock_kafka_producer: MagicMock,
):
    claimed_jobs = [
        PortfolioAggregationJob(
            portfolio_id="P1",
            aggregation_date=date(2025, 8, 11),
            correlation_id="corr-agg-1",
        ),
    ]

    await scheduler._dispatch_jobs(claimed_jobs)

    mock_kafka_producer.publish_message.assert_called_once_with(
        topic=KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC,
        key="P1",
        value={
            "portfolio_id": "P1",
            "aggregation_date": "2025-08-11",
            "correlation_id": "corr-agg-1",
        },
        headers=[("correlation_id", b"corr-agg-1")],
    )
    mock_kafka_producer.flush.assert_called_once_with(timeout=10)


async def test_scheduler_omits_empty_correlation_header(
    scheduler: AggregationScheduler,
    mock_kafka_producer: MagicMock,
):
    claimed_jobs = [
        PortfolioAggregationJob(
            portfolio_id="P2",
            aggregation_date=date(2025, 8, 12),
            correlation_id=None,
        ),
    ]

    await scheduler._dispatch_jobs(claimed_jobs)

    mock_kafka_producer.publish_message.assert_called_once_with(
        topic=KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC,
        key="P2",
        value={
            "portfolio_id": "P2",
            "aggregation_date": "2025-08-12",
            "correlation_id": None,
        },
        headers=[],
    )
    mock_kafka_producer.flush.assert_called_once_with(timeout=10)


async def test_scheduler_reads_runtime_settings_from_environment(
    mock_kafka_producer: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AGGREGATION_SCHEDULER_POLL_INTERVAL_SECONDS", "9")
    monkeypatch.setenv("AGGREGATION_SCHEDULER_BATCH_SIZE", "17")
    monkeypatch.setenv("AGGREGATION_SCHEDULER_STALE_TIMEOUT_MINUTES", "13")
    monkeypatch.setenv("AGGREGATION_SCHEDULER_MAX_ATTEMPTS", "6")

    with patch(
        "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.get_kafka_producer",
        return_value=mock_kafka_producer,
    ):
        scheduler = AggregationScheduler()

    assert scheduler._poll_interval == 9
    assert scheduler._batch_size == 17
    assert scheduler._stale_timeout_minutes == 13
    assert scheduler._max_attempts == 6
