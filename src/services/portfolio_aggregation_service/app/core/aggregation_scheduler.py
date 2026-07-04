import asyncio
import logging
from datetime import timezone

from portfolio_common.scheduler_dispatch_recovery import (
    SchedulerDispatchError,
    dispatch_failure_reason,
)

from ..infrastructure.aggregation_scheduler_adapters import (
    PrometheusAggregationSchedulerMetricsSink,
    SqlAlchemyAggregationSchedulerRepositoryProvider,
    SystemAggregationSchedulerClock,
)
from ..ports.aggregation_scheduler_ports import (
    AggregationSchedulerClock,
    AggregationSchedulerMetricsSink,
    AggregationSchedulerRepository,
    AggregationSchedulerRepositoryProvider,
)
from ..settings import AggregationRuntimeSettings, get_aggregation_runtime_settings
from .aggregation_job_publisher import (
    AggregationJobPublisher,
    get_aggregation_job_publisher,
    plan_aggregation_job_dispatch,
    publish_aggregation_dispatch_plan,
)

logger = logging.getLogger(__name__)


class AggregationScheduler:
    def __init__(
        self,
        poll_interval: int = 5,
        batch_size: int = 100,
        *,
        settings: AggregationRuntimeSettings | None = None,
        repository_provider: AggregationSchedulerRepositoryProvider | None = None,
        metrics_sink: AggregationSchedulerMetricsSink | None = None,
        clock: AggregationSchedulerClock | None = None,
        aggregation_job_publisher: AggregationJobPublisher | None = None,
    ):
        runtime_settings = settings or get_aggregation_runtime_settings(
            scheduler_poll_interval_default=poll_interval,
            scheduler_batch_size_default=batch_size,
        )
        self._poll_interval = runtime_settings.aggregation_scheduler_poll_interval_seconds
        self._batch_size = runtime_settings.aggregation_scheduler_batch_size
        self._stale_timeout_minutes = runtime_settings.aggregation_scheduler_stale_timeout_minutes
        self._max_attempts = runtime_settings.aggregation_scheduler_max_attempts
        self._repository_provider = (
            repository_provider or SqlAlchemyAggregationSchedulerRepositoryProvider()
        )
        self._metrics_sink = metrics_sink or PrometheusAggregationSchedulerMetricsSink()
        self._clock = clock or SystemAggregationSchedulerClock()
        self._publisher = aggregation_job_publisher or get_aggregation_job_publisher()
        self._running = True
        self._stop_event = asyncio.Event()

    def stop(self):
        logger.info("Aggregation scheduler shutdown signal received.")
        self._running = False
        self._stop_event.set()

    async def _update_queue_metrics(self, repo: AggregationSchedulerRepository) -> None:
        queue_stats = await repo.get_job_queue_stats()
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

    async def _dispatch_jobs(self, jobs) -> None:
        if not jobs:
            return

        logger.info(f"Dispatching {len(jobs)} claimed aggregation jobs to Kafka.")
        plan = plan_aggregation_job_dispatch(jobs)
        publish_aggregation_dispatch_plan(plan=plan, publisher=self._publisher)
        logger.info(f"Successfully flushed {len(jobs)} aggregation jobs.")

    async def _recover_dispatch_failure(self, failure: SchedulerDispatchError) -> None:
        if not failure.recovery_job_ids:
            logger.warning(
                "Aggregation scheduler dispatch failure had no durable job ids to recover.",
                extra={
                    "failure_phase": failure.failure_phase,
                    "record_keys": list(failure.recovery_record_keys),
                    "published_record_keys": list(failure.published_record_keys),
                },
            )
            return

        async def recover(repo: AggregationSchedulerRepository) -> None:
            await repo.recover_dispatch_failed_jobs(
                list(failure.recovery_job_ids),
                max_attempts=self._max_attempts,
                failure_reason=dispatch_failure_reason(
                    failure_phase=failure.failure_phase,
                    record_keys=failure.recovery_record_keys,
                ),
            )

        await self._repository_provider.run_in_transaction(recover)

    async def _claim_jobs_for_poll(self, repo: AggregationSchedulerRepository):
        await self._update_queue_metrics(repo)
        await repo.find_and_reset_stale_jobs(
            timeout_minutes=self._stale_timeout_minutes,
            max_attempts=self._max_attempts,
        )
        claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
        await self._update_queue_metrics(repo)
        return claimed_jobs

    async def _run_poll_once(self) -> None:
        claimed_jobs = await self._repository_provider.run_in_transaction(self._claim_jobs_for_poll)
        if not claimed_jobs:
            logger.info("Scheduler poll found no eligible jobs.")
            return

        logger.info(f"Scheduler claimed {len(claimed_jobs)} jobs for processing.")
        try:
            await self._dispatch_jobs(claimed_jobs)
        except SchedulerDispatchError as exc:
            await self._recover_dispatch_failure(exc)
            raise

    async def _wait_for_next_poll_or_stop(self) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
            return False
        except asyncio.TimeoutError:
            return True
        except asyncio.CancelledError:
            return False

    async def run(self):
        logger.info(f"AggregationScheduler started. Polling every {self._poll_interval} seconds.")
        while self._running:
            try:
                await self._run_poll_once()
            except Exception:
                logger.error("Error in scheduler polling loop.", exc_info=True)

            if not await self._wait_for_next_poll_or_stop():
                break

        logger.info("AggregationScheduler has stopped.")
