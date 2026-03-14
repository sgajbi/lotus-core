import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.config import KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.kafka_utils import KafkaProducer

from src.services.portfolio_aggregation_service.app.core.aggregation_scheduler import (
    AggregationScheduler,
)
from src.services.portfolio_aggregation_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    mock = MagicMock(spec=KafkaProducer)
    mock.flush.return_value = 0
    return mock


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


async def test_scheduler_flushes_and_raises_with_remaining_keys_on_partial_dispatch_failure(
    scheduler: AggregationScheduler,
    mock_kafka_producer: MagicMock,
):
    claimed_jobs = [
        PortfolioAggregationJob(
            portfolio_id="P1",
            aggregation_date=date(2025, 8, 11),
            correlation_id="corr-agg-1",
        ),
        PortfolioAggregationJob(
            portfolio_id="P2",
            aggregation_date=date(2025, 8, 12),
            correlation_id="corr-agg-2",
        ),
    ]
    mock_kafka_producer.publish_message.side_effect = [None, RuntimeError("broker timeout")]

    with pytest.raises(RuntimeError, match="Remaining job keys: P2\\|2025-08-12"):
        await scheduler._dispatch_jobs(claimed_jobs)

    mock_kafka_producer.flush.assert_called_once_with(timeout=10)


async def test_scheduler_raises_on_flush_timeout(
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
    mock_kafka_producer.flush.return_value = 1

    with pytest.raises(
        RuntimeError,
        match="Delivery confirmation timed out while dispatching aggregation jobs",
    ):
        await scheduler._dispatch_jobs(claimed_jobs)


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


async def test_scheduler_updates_queue_metrics():
    repo = AsyncMock(spec=TimeseriesRepository)
    repo.get_job_queue_stats.return_value = {
        "pending_count": 3,
        "failed_count": 1,
        "oldest_pending_created_at": datetime(2025, 8, 12, 0, 0, tzinfo=timezone.utc),
    }

    with (
        patch(
            "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.get_kafka_producer",
            return_value=MagicMock(spec=KafkaProducer),
        ),
        patch(
            "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.set_control_queue_pending"
        ) as mock_set_pending,
        patch(
            "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.set_control_queue_failed_stored"
        ) as mock_set_failed,
        patch(
            "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.set_control_queue_oldest_pending_age_seconds"
        ) as mock_set_oldest,
        patch(
            "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.datetime"
        ) as mock_datetime,
    ):
        scheduler = AggregationScheduler()
        mock_datetime.now.return_value = datetime(2025, 8, 12, 0, 2, tzinfo=timezone.utc)
        mock_datetime.side_effect = datetime

        await scheduler._update_queue_metrics(repo)

    mock_set_pending.assert_called_once_with("aggregation", 3)
    mock_set_failed.assert_called_once_with("aggregation", 1)
    mock_set_oldest.assert_called_once_with("aggregation", 120.0)


async def test_scheduler_stop_interrupts_poll_sleep(
    mock_kafka_producer: MagicMock,
):
    with patch(
        "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.get_kafka_producer",
        return_value=mock_kafka_producer,
    ):
        scheduler = AggregationScheduler(poll_interval=60)

    batch_started = asyncio.Event()
    mock_repo = AsyncMock(spec=TimeseriesRepository)
    mock_repo.find_and_claim_eligible_jobs.return_value = []

    async def update_queue_metrics(repo):
        batch_started.set()

    class _DbSession:
        @asynccontextmanager
        async def begin(self):
            yield self

    mock_db_session = _DbSession()

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.portfolio_aggregation_service.app.core.aggregation_scheduler.TimeseriesRepository",
            return_value=mock_repo,
        ),
        patch.object(scheduler, "_update_queue_metrics", side_effect=update_queue_metrics),
    ):
        task = asyncio.create_task(scheduler.run())
        await batch_started.wait()
        await asyncio.sleep(0)

        scheduler.stop()

        await asyncio.wait_for(task, timeout=0.2)
