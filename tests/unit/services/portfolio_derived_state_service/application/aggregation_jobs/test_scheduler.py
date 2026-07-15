"""Prove lease-aware portfolio aggregation scheduling."""

import asyncio
from datetime import date, datetime, timezone

import pytest

from src.services.portfolio_derived_state_service.app.application.aggregation_jobs import (
    AggregationScheduler,
)
from src.services.portfolio_derived_state_service.app.domain.aggregation_jobs.models import (
    AggregationJobBatchResult,
    AggregationJobLease,
    ClaimedAggregationJob,
    ExpiredAggregationJobRecovery,
)

pytestmark = pytest.mark.asyncio


class FakeRepository:
    def __init__(self, jobs: list[ClaimedAggregationJob] | None = None) -> None:
        self.jobs = jobs or []
        self.recovery_calls = []
        self.claim_calls = []
        self.poll_entered = asyncio.Event()

    async def get_job_queue_stats(self):
        return {
            "pending_count": 2,
            "failed_count": 1,
            "oldest_pending_created_at": datetime(2026, 7, 15, 7, 58, tzinfo=timezone.utc),
        }

    async def recover_expired_job_leases(self, *, now, max_attempts):
        self.poll_entered.set()
        self.recovery_calls.append((now, max_attempts))
        return ExpiredAggregationJobRecovery(requeued_count=1, failed_count=0)

    async def claim_eligible_jobs(self, *, batch_size, lease):
        self.claim_calls.append((batch_size, lease))
        return self.jobs


class FakeProvider:
    def __init__(self, repository: FakeRepository) -> None:
        self.repository = repository

    async def run_in_transaction(self, operation):
        return await operation(self.repository)


class FakeProcessor:
    def __init__(self) -> None:
        self.batches = []

    async def process(self, jobs):
        self.batches.append(jobs)
        return AggregationJobBatchResult(complete_count=len(jobs))


class FakeMetrics:
    def __init__(self) -> None:
        self.pending = []
        self.failed = []
        self.oldest = []
        self.recoveries = []
        self.claimed = []
        self.processed = []

    def set_pending(self, count):
        self.pending.append(count)

    def set_failed(self, count):
        self.failed.append(count)

    def set_oldest_pending_age_seconds(self, age_seconds):
        self.oldest.append(age_seconds)

    def observe_recovery(self, recovery):
        self.recoveries.append(recovery)

    def observe_claimed(self, count):
        self.claimed.append(count)

    def observe_processed(self, result):
        self.processed.append(result)


class FixedClock:
    def now_utc(self):
        return datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


class FixedTokenGenerator:
    def new_hex(self):
        return "lease-token-1"


def _claimed_job() -> ClaimedAggregationJob:
    return ClaimedAggregationJob(
        id=7,
        portfolio_id="PORT-7",
        aggregation_date=date(2026, 7, 15),
        correlation_id="corr-7",
        lease=AggregationJobLease(
            owner="aggregation-runtime-1",
            token="lease-token-1",
            expires_at=datetime(2026, 7, 15, 8, 5, tzinfo=timezone.utc),
        ),
    )


def _scheduler(repository, processor, metrics=None):
    return AggregationScheduler(
        poll_interval_seconds=60,
        batch_size=17,
        lease_duration_seconds=300,
        max_attempts=6,
        lease_owner="aggregation-runtime-1",
        repository_provider=FakeProvider(repository),
        job_processor=processor,
        metrics_sink=metrics or FakeMetrics(),
        clock=FixedClock(),
        token_generator=FixedTokenGenerator(),
    )


async def test_scheduler_recovers_expiry_then_leases_and_processes_ready_batch() -> None:
    job = _claimed_job()
    repository = FakeRepository([job])
    processor = FakeProcessor()
    metrics = FakeMetrics()
    scheduler = _scheduler(repository, processor, metrics)

    await scheduler._run_poll_once()

    assert repository.recovery_calls == [(FixedClock().now_utc(), 6)]
    batch_size, lease = repository.claim_calls[0]
    assert batch_size == 17
    assert lease == job.lease
    assert processor.batches == [[job]]
    assert metrics.pending == [2, 2]
    assert metrics.failed == [1, 1]
    assert metrics.oldest == [120.0, 120.0]
    assert metrics.recoveries == [ExpiredAggregationJobRecovery(requeued_count=1, failed_count=0)]
    assert metrics.claimed == [1]
    assert metrics.processed == [AggregationJobBatchResult(complete_count=1)]


async def test_scheduler_stop_interrupts_poll_wait() -> None:
    repository = FakeRepository()
    scheduler = _scheduler(repository, FakeProcessor())

    task = asyncio.create_task(scheduler.run())
    await repository.poll_entered.wait()
    scheduler.stop()

    await asyncio.wait_for(task, timeout=0.2)
