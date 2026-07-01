import asyncio
import logging
from datetime import datetime, timezone
from typing import List

from portfolio_common.config import KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.db import get_async_db_session
from portfolio_common.events import PortfolioAggregationRequiredEvent, event_business_payload
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.monitoring import (
    set_control_queue_failed_stored,
    set_control_queue_oldest_pending_age_seconds,
    set_control_queue_pending,
)
from portfolio_common.scheduler_dispatch_recovery import (
    DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
    DISPATCH_PUBLISH_FAILURE_PHASE,
    SchedulerDispatchError,
    dispatch_failure_reason,
    present_job_ids,
)

from ..repositories.timeseries_repository import TimeseriesRepository
from ..settings import get_aggregation_runtime_settings

# src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py


logger = logging.getLogger(__name__)


class AggregationScheduler:
    def __init__(self, poll_interval: int = 5, batch_size: int = 100):
        runtime_settings = get_aggregation_runtime_settings(
            scheduler_poll_interval_default=poll_interval,
            scheduler_batch_size_default=batch_size,
        )
        self._poll_interval = runtime_settings.aggregation_scheduler_poll_interval_seconds
        self._batch_size = runtime_settings.aggregation_scheduler_batch_size
        self._stale_timeout_minutes = runtime_settings.aggregation_scheduler_stale_timeout_minutes
        self._max_attempts = runtime_settings.aggregation_scheduler_max_attempts
        self._running = True
        self._stop_event = asyncio.Event()
        self._producer: KafkaProducer = get_kafka_producer()

    def stop(self):
        logger.info("Aggregation scheduler shutdown signal received.")
        self._running = False
        self._stop_event.set()

    async def _update_queue_metrics(self, repo: TimeseriesRepository):
        queue_stats = await repo.get_job_queue_stats()
        set_control_queue_pending("aggregation", queue_stats["pending_count"])
        set_control_queue_failed_stored("aggregation", queue_stats["failed_count"])
        oldest_pending_created_at = queue_stats["oldest_pending_created_at"]
        if oldest_pending_created_at is None:
            set_control_queue_oldest_pending_age_seconds("aggregation", 0.0)
            return
        age_seconds = (
            datetime.now(timezone.utc) - oldest_pending_created_at.astimezone(timezone.utc)
        ).total_seconds()
        set_control_queue_oldest_pending_age_seconds("aggregation", max(age_seconds, 0.0))

    async def _dispatch_jobs(self, jobs: List[PortfolioAggregationJob]):
        if not jobs:
            return

        logger.info(f"Dispatching {len(jobs)} claimed aggregation jobs to Kafka.")
        record_keys = [f"{job.portfolio_id}|{job.aggregation_date.isoformat()}" for job in jobs]
        for idx, job in enumerate(jobs):
            record_key = record_keys[idx]
            event = PortfolioAggregationRequiredEvent(
                portfolio_id=job.portfolio_id,
                aggregation_date=job.aggregation_date,
                correlation_id=job.correlation_id,
            )
            headers = []
            if job.correlation_id:
                headers.append(("correlation_id", job.correlation_id.encode("utf-8")))
            try:
                self._producer.publish_message(
                    topic=KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC,
                    key=record_key,
                    value=event_business_payload(
                        event,
                        include_correlation_id=True,
                        mode="json",
                    ),
                    headers=headers,
                )
            except Exception as exc:
                undelivered_count = self._producer.flush(timeout=10)
                if undelivered_count:
                    affected_keys = ", ".join(record_keys)
                    raise SchedulerDispatchError(
                        message=(
                            "Delivery confirmation timed out while recovering from aggregation "
                            f"dispatch failure. Affected job keys: {affected_keys}."
                        ),
                        recovery_job_ids=present_job_ids(jobs),
                        recovery_record_keys=tuple(record_keys),
                        published_record_keys=tuple(record_keys[:idx]),
                        failure_phase=DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
                    ) from exc
                remaining_keys = ", ".join(record_keys[idx:])
                raise SchedulerDispatchError(
                    message=(
                        "Failed to dispatch aggregation jobs after "
                        f"{idx} earlier job(s) were queued. Remaining job keys: {remaining_keys}."
                    ),
                    recovery_job_ids=present_job_ids(jobs[idx:]),
                    recovery_record_keys=tuple(record_keys[idx:]),
                    published_record_keys=tuple(record_keys[:idx]),
                    failure_phase=DISPATCH_PUBLISH_FAILURE_PHASE,
                ) from exc
        undelivered_count = self._producer.flush(timeout=10)
        if undelivered_count:
            affected_keys = ", ".join(record_keys)
            raise SchedulerDispatchError(
                message=(
                    "Delivery confirmation timed out while dispatching aggregation jobs. "
                    f"Affected job keys: {affected_keys}."
                ),
                recovery_job_ids=present_job_ids(jobs),
                recovery_record_keys=tuple(record_keys),
                published_record_keys=tuple(record_keys),
                failure_phase=DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
            )
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
        async for db in get_async_db_session():
            async with db.begin():
                repo = TimeseriesRepository(db)
                await repo.recover_dispatch_failed_jobs(
                    list(failure.recovery_job_ids),
                    max_attempts=self._max_attempts,
                    failure_reason=dispatch_failure_reason(
                        failure_phase=failure.failure_phase,
                        record_keys=failure.recovery_record_keys,
                    ),
                )

    async def run(self):
        logger.info(f"AggregationScheduler started. Polling every {self._poll_interval} seconds.")
        while self._running:
            try:
                async for db in get_async_db_session():
                    async with db.begin():
                        repo = TimeseriesRepository(db)
                        await self._update_queue_metrics(repo)

                        await repo.find_and_reset_stale_jobs(
                            timeout_minutes=self._stale_timeout_minutes,
                            max_attempts=self._max_attempts,
                        )
                        claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
                        await self._update_queue_metrics(repo)

                if claimed_jobs:
                    logger.info(f"Scheduler claimed {len(claimed_jobs)} jobs for processing.")
                    try:
                        await self._dispatch_jobs(claimed_jobs)
                    except SchedulerDispatchError as exc:
                        await self._recover_dispatch_failure(exc)
                        raise
                else:
                    logger.info("Scheduler poll found no eligible jobs.")

            except Exception:
                logger.error("Error in scheduler polling loop.", exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

        logger.info("AggregationScheduler has stopped.")
