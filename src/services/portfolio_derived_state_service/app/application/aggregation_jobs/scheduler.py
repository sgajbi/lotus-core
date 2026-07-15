"""Application scheduler for durable portfolio aggregation jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta, timezone

from ...domain.aggregation_jobs.models import AggregationJobLease, ClaimedAggregationJob
from ...ports.aggregation_scheduler_ports import (
    AggregationJobBatchProcessor,
    AggregationLeaseTokenGenerator,
    AggregationSchedulerClock,
    AggregationSchedulerMetricsSink,
    AggregationSchedulerRepository,
    AggregationSchedulerRepositoryProvider,
)

logger = logging.getLogger(__name__)


class AggregationScheduler:
    """Recover expired claims, lease ready work, and invoke bounded workers."""

    def __init__(
        self,
        *,
        poll_interval_seconds: int,
        batch_size: int,
        lease_duration_seconds: int,
        max_attempts: int,
        lease_owner: str,
        repository_provider: AggregationSchedulerRepositoryProvider,
        job_processor: AggregationJobBatchProcessor,
        metrics_sink: AggregationSchedulerMetricsSink,
        clock: AggregationSchedulerClock,
        token_generator: AggregationLeaseTokenGenerator,
    ) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._batch_size = batch_size
        self._lease_duration_seconds = lease_duration_seconds
        self._max_attempts = max_attempts
        self._lease_owner = lease_owner
        self._repository_provider = repository_provider
        self._job_processor = job_processor
        self._metrics_sink = metrics_sink
        self._clock = clock
        self._token_generator = token_generator
        self._running = True
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        """Interrupt the scheduler poll loop."""

        self._running = False
        self._stop_event.set()

    async def _update_queue_metrics(self, repository: AggregationSchedulerRepository) -> None:
        queue_stats = await repository.get_job_queue_stats()
        self._metrics_sink.set_pending(queue_stats["pending_count"])
        self._metrics_sink.set_failed(queue_stats["failed_count"])
        oldest_pending_created_at = queue_stats["oldest_pending_created_at"]
        if oldest_pending_created_at is None:
            self._metrics_sink.set_oldest_pending_age_seconds(0.0)
            return
        age_seconds = (
            self._clock.now_utc() - oldest_pending_created_at.astimezone(timezone.utc)
        ).total_seconds()
        self._metrics_sink.set_oldest_pending_age_seconds(max(age_seconds, 0.0))

    async def _claim_jobs_for_poll(
        self,
        repository: AggregationSchedulerRepository,
    ) -> list[ClaimedAggregationJob]:
        await self._update_queue_metrics(repository)
        now = self._clock.now_utc()
        recovery = await repository.recover_expired_job_leases(
            now=now,
            max_attempts=self._max_attempts,
        )
        self._metrics_sink.observe_recovery(recovery)
        jobs = await repository.claim_eligible_jobs(
            batch_size=self._batch_size,
            lease=AggregationJobLease(
                owner=self._lease_owner,
                token=self._token_generator.new_hex(),
                expires_at=now + timedelta(seconds=self._lease_duration_seconds),
            ),
        )
        self._metrics_sink.observe_claimed(len(jobs))
        await self._update_queue_metrics(repository)
        return jobs

    async def _run_poll_once(self) -> None:
        jobs = await self._repository_provider.run_in_transaction(self._claim_jobs_for_poll)
        if not jobs:
            return
        result = await self._job_processor.process(jobs)
        self._metrics_sink.observe_processed(result)
        logger.info(
            "Processed claimed aggregation job batch.",
            extra={
                "claimed_count": len(jobs),
                "processed_count": result.processed_count,
                "lost_ownership_count": result.lost_ownership_count,
                "execution_error_count": result.execution_error_count,
            },
        )

    async def _wait_for_next_poll_or_stop(self) -> bool:
        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=self._poll_interval_seconds,
            )
            return False
        except TimeoutError:
            return True
        except asyncio.CancelledError:
            return False

    async def run(self) -> None:
        """Poll until shutdown while isolating one failed poll from the next."""

        while self._running:
            try:
                await self._run_poll_once()
            except Exception:
                logger.error("Aggregation scheduler poll failed.", exc_info=True)
            if not await self._wait_for_next_poll_or_stop():
                break
