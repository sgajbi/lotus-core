import asyncio
from datetime import date, datetime, timezone

import pytest
from portfolio_common.config import KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.scheduler_dispatch_recovery import (
    DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
    DISPATCH_PUBLISH_FAILURE_PHASE,
    SchedulerDispatchError,
)

from src.services.portfolio_aggregation_service.app.core.aggregation_job_publisher import (
    AggregationJobDispatchMessage,
    aggregation_job_record_key,
    plan_aggregation_job_dispatch,
)
from src.services.portfolio_aggregation_service.app.core.aggregation_scheduler import (
    AggregationScheduler,
)
from src.services.portfolio_aggregation_service.app.settings import AggregationRuntimeSettings

pytestmark = pytest.mark.asyncio


class FakeAggregationJobPublisher:
    def __init__(self, *, fail_at: int | None = None, undelivered_count: int = 0) -> None:
        self.fail_at = fail_at
        self.undelivered_count = undelivered_count
        self.published: list[AggregationJobDispatchMessage] = []
        self.confirm_delivery_calls: list[int] = []

    def publish_job_requested(self, message: AggregationJobDispatchMessage) -> None:
        if self.fail_at is not None and len(self.published) == self.fail_at:
            raise RuntimeError("broker timeout")
        self.published.append(message)

    def confirm_delivery(self, *, timeout_seconds: int) -> int:
        self.confirm_delivery_calls.append(timeout_seconds)
        return self.undelivered_count


class FakeAggregationRepository:
    def __init__(self, *, claimed_jobs=None) -> None:
        self.claimed_jobs = list(claimed_jobs or [])
        self.queue_stats = {
            "pending_count": 3,
            "failed_count": 1,
            "oldest_pending_created_at": datetime(2025, 8, 12, 0, 0, tzinfo=timezone.utc),
        }
        self.reset_calls: list[dict[str, int]] = []
        self.claim_calls: list[int] = []
        self.recovered: list[dict[str, object]] = []
        self.poll_entered = asyncio.Event()

    async def get_job_queue_stats(self):
        return self.queue_stats

    async def find_and_reset_stale_jobs(
        self,
        *,
        timeout_minutes: int,
        max_attempts: int,
    ) -> int:
        self.poll_entered.set()
        self.reset_calls.append(
            {
                "timeout_minutes": timeout_minutes,
                "max_attempts": max_attempts,
            }
        )
        return 0

    async def find_and_claim_eligible_jobs(self, batch_size: int):
        self.claim_calls.append(batch_size)
        return self.claimed_jobs

    async def recover_dispatch_failed_jobs(
        self,
        job_ids: list[int],
        *,
        max_attempts: int,
        failure_reason: str,
    ) -> None:
        self.recovered.append(
            {
                "job_ids": job_ids,
                "max_attempts": max_attempts,
                "failure_reason": failure_reason,
            }
        )


class FakeRepositoryProvider:
    def __init__(self, repository: FakeAggregationRepository) -> None:
        self.repository = repository
        self.transaction_count = 0

    async def run_in_transaction(self, operation):
        self.transaction_count += 1
        return await operation(self.repository)


class FakeMetricsSink:
    def __init__(self) -> None:
        self.pending: list[int] = []
        self.failed: list[int] = []
        self.oldest_pending_age_seconds: list[float] = []

    def set_pending(self, count: int) -> None:
        self.pending.append(count)

    def set_failed(self, count: int) -> None:
        self.failed.append(count)

    def set_oldest_pending_age_seconds(self, age_seconds: float) -> None:
        self.oldest_pending_age_seconds.append(age_seconds)


class FixedClock:
    def now_utc(self) -> datetime:
        return datetime(2025, 8, 12, 0, 2, tzinfo=timezone.utc)


def _settings() -> AggregationRuntimeSettings:
    return AggregationRuntimeSettings(
        portfolio_aggregation_consumer_count=1,
        aggregation_scheduler_poll_interval_seconds=60,
        aggregation_scheduler_batch_size=17,
        aggregation_scheduler_stale_timeout_minutes=13,
        aggregation_scheduler_max_attempts=6,
    )


def _job(
    *,
    job_id: int | None = None,
    portfolio_id: str = "P1",
    aggregation_date: date = date(2025, 8, 11),
    correlation_id: str | None = "corr-agg-1",
) -> PortfolioAggregationJob:
    return PortfolioAggregationJob(
        id=job_id,
        portfolio_id=portfolio_id,
        aggregation_date=aggregation_date,
        correlation_id=correlation_id,
    )


def _scheduler(
    *,
    repository: FakeAggregationRepository | None = None,
    publisher: FakeAggregationJobPublisher | None = None,
    settings: AggregationRuntimeSettings | None = None,
    metrics_sink: FakeMetricsSink | None = None,
) -> AggregationScheduler:
    return AggregationScheduler(
        settings=settings or _settings(),
        repository_provider=FakeRepositoryProvider(repository or FakeAggregationRepository()),
        metrics_sink=metrics_sink or FakeMetricsSink(),
        clock=FixedClock(),
        aggregation_job_publisher=publisher or FakeAggregationJobPublisher(),
    )


async def test_plan_aggregation_job_dispatch_builds_event_payload_key_and_header():
    plan = plan_aggregation_job_dispatch([_job(portfolio_id="P1")])

    assert len(plan.messages) == 1
    message = plan.messages[0]
    assert message.topic == KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC
    assert message.record_key == "P1|2025-08-11"
    assert message.value == {
        "portfolio_id": "P1",
        "aggregation_date": "2025-08-11",
        "correlation_id": "corr-agg-1",
    }
    assert message.headers == [("correlation_id", b"corr-agg-1")]


async def test_plan_aggregation_job_dispatch_omits_empty_correlation_header():
    plan = plan_aggregation_job_dispatch([_job(portfolio_id="P2", correlation_id=None)])

    assert plan.messages[0].record_key == "P2|2025-08-11"
    assert plan.messages[0].headers == []


async def test_aggregation_job_record_key_uses_portfolio_and_business_date():
    assert aggregation_job_record_key(_job(portfolio_id="P9")) == "P9|2025-08-11"


async def test_scheduler_dispatch_no_jobs_skips_publisher_confirmation():
    publisher = FakeAggregationJobPublisher()
    scheduler = _scheduler(publisher=publisher)

    await scheduler._dispatch_jobs([])

    assert publisher.published == []
    assert publisher.confirm_delivery_calls == []


async def test_scheduler_dispatches_claimed_jobs_through_publisher_port():
    publisher = FakeAggregationJobPublisher()
    scheduler = _scheduler(publisher=publisher)

    await scheduler._dispatch_jobs([_job(portfolio_id="P1")])

    assert [message.record_key for message in publisher.published] == ["P1|2025-08-11"]
    assert publisher.confirm_delivery_calls == [10]


async def test_scheduler_partial_dispatch_failure_recovers_only_unpublished_jobs():
    publisher = FakeAggregationJobPublisher(fail_at=1)
    scheduler = _scheduler(publisher=publisher)
    jobs = [
        _job(job_id=201, portfolio_id="P1"),
        _job(
            job_id=202,
            portfolio_id="P2",
            aggregation_date=date(2025, 8, 12),
            correlation_id="corr-agg-2",
        ),
    ]

    with pytest.raises(SchedulerDispatchError) as exc_info:
        await scheduler._dispatch_jobs(jobs)

    assert exc_info.value.failure_phase == DISPATCH_PUBLISH_FAILURE_PHASE
    assert exc_info.value.recovery_job_ids == (202,)
    assert exc_info.value.recovery_record_keys == ("P2|2025-08-12",)
    assert exc_info.value.published_record_keys == ("P1|2025-08-11",)
    assert [message.record_key for message in publisher.published] == ["P1|2025-08-11"]


async def test_scheduler_partial_dispatch_flush_timeout_recovers_all_claimed_jobs():
    publisher = FakeAggregationJobPublisher(fail_at=1, undelivered_count=1)
    scheduler = _scheduler(publisher=publisher)
    jobs = [
        _job(job_id=211, portfolio_id="P1"),
        _job(job_id=212, portfolio_id="P2", aggregation_date=date(2025, 8, 12)),
    ]

    with pytest.raises(
        SchedulerDispatchError,
        match="Delivery confirmation timed out while recovering from aggregation dispatch failure",
    ) as exc_info:
        await scheduler._dispatch_jobs(jobs)

    assert exc_info.value.failure_phase == DISPATCH_CONFIRMATION_TIMEOUT_PHASE
    assert exc_info.value.recovery_job_ids == (211, 212)
    assert exc_info.value.recovery_record_keys == ("P1|2025-08-11", "P2|2025-08-12")
    assert exc_info.value.published_record_keys == ("P1|2025-08-11",)


async def test_scheduler_raises_on_flush_timeout():
    publisher = FakeAggregationJobPublisher(undelivered_count=1)
    scheduler = _scheduler(publisher=publisher)

    with pytest.raises(
        SchedulerDispatchError,
        match="Delivery confirmation timed out while dispatching aggregation jobs",
    ) as exc_info:
        await scheduler._dispatch_jobs([_job(job_id=301, portfolio_id="P1")])

    assert exc_info.value.failure_phase == DISPATCH_CONFIRMATION_TIMEOUT_PHASE
    assert exc_info.value.recovery_job_ids == (301,)
    assert exc_info.value.recovery_record_keys == ("P1|2025-08-11",)
    assert exc_info.value.published_record_keys == ("P1|2025-08-11",)


async def test_scheduler_run_poll_once_resets_stale_jobs_claims_batch_and_updates_metrics():
    repository = FakeAggregationRepository(claimed_jobs=[])
    metrics_sink = FakeMetricsSink()
    scheduler = _scheduler(repository=repository, metrics_sink=metrics_sink)

    await scheduler._run_poll_once()

    assert repository.reset_calls == [{"timeout_minutes": 13, "max_attempts": 6}]
    assert repository.claim_calls == [17]
    assert metrics_sink.pending == [3, 3]
    assert metrics_sink.failed == [1, 1]
    assert metrics_sink.oldest_pending_age_seconds == [120.0, 120.0]


async def test_scheduler_run_poll_once_recovers_dispatch_failure_before_next_poll():
    repository = FakeAggregationRepository(claimed_jobs=[_job(job_id=401, portfolio_id="P1")])
    publisher = FakeAggregationJobPublisher(fail_at=0)
    scheduler = _scheduler(repository=repository, publisher=publisher)

    with pytest.raises(SchedulerDispatchError):
        await scheduler._run_poll_once()

    assert repository.recovered == [
        {
            "job_ids": [401],
            "max_attempts": 6,
            "failure_reason": (
                "Scheduler dispatch publish failed before queueing record keys: P1|2025-08-11"
            ),
        }
    ]


async def test_scheduler_reads_runtime_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AGGREGATION_SCHEDULER_POLL_INTERVAL_SECONDS", "9")
    monkeypatch.setenv("AGGREGATION_SCHEDULER_BATCH_SIZE", "17")
    monkeypatch.setenv("AGGREGATION_SCHEDULER_STALE_TIMEOUT_MINUTES", "13")
    monkeypatch.setenv("AGGREGATION_SCHEDULER_MAX_ATTEMPTS", "6")

    scheduler = AggregationScheduler(
        repository_provider=FakeRepositoryProvider(FakeAggregationRepository()),
        metrics_sink=FakeMetricsSink(),
        clock=FixedClock(),
        aggregation_job_publisher=FakeAggregationJobPublisher(),
    )

    assert scheduler._poll_interval == 9
    assert scheduler._batch_size == 17
    assert scheduler._stale_timeout_minutes == 13
    assert scheduler._max_attempts == 6


async def test_scheduler_stop_interrupts_poll_sleep():
    repository = FakeAggregationRepository(claimed_jobs=[])
    provider = FakeRepositoryProvider(repository)
    scheduler = AggregationScheduler(
        settings=_settings(),
        repository_provider=provider,
        metrics_sink=FakeMetricsSink(),
        clock=FixedClock(),
        aggregation_job_publisher=FakeAggregationJobPublisher(),
    )

    task = asyncio.create_task(scheduler.run())
    await repository.poll_entered.wait()
    await asyncio.sleep(0)

    scheduler.stop()

    await asyncio.wait_for(task, timeout=0.2)
