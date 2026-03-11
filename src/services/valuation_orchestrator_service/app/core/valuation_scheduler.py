# src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List

from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from portfolio_common.database_models import PortfolioValuationJob
from portfolio_common.db import get_async_db_session
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.monitoring import (
    INSTRUMENT_REPROCESSING_TRIGGERS_PENDING,
    POSITION_STATE_WATERMARK_LAG_DAYS,
    REPROCESSING_ACTIVE_KEYS_TOTAL,
    SCHEDULER_GAP_DAYS,
    SNAPSHOT_LAG_SECONDS,
    VALUATION_JOBS_CREATED_TOTAL,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository

from ..repositories.valuation_repository import ValuationRepository
from ..settings import get_valuation_runtime_settings

logger = logging.getLogger(__name__)


class ValuationScheduler:
    """
    A background task that drives all valuation activity. It polls the position_state
    table to find keys that need backfilling, creates the necessary valuation jobs,
    dispatches them, and advances watermarks upon completion.
    """

    def __init__(self, poll_interval: int = 30, batch_size: int = 100):
        runtime_settings = get_valuation_runtime_settings(
            scheduler_poll_interval_default=poll_interval,
            scheduler_batch_size_default=batch_size,
            scheduler_dispatch_rounds_default=3,
        )
        self._poll_interval = runtime_settings.valuation_scheduler_poll_interval_seconds
        self._batch_size = runtime_settings.valuation_scheduler_batch_size
        self._dispatch_rounds_per_poll = runtime_settings.valuation_scheduler_dispatch_rounds
        self._running = True
        self._producer: KafkaProducer = get_kafka_producer()

    def stop(self):
        """Signals the scheduler to gracefully shut down."""
        logger.info("Valuation scheduler shutdown signal received.")
        self._running = False

    async def _update_reprocessing_metrics(self, db):
        """Queries for and sets key gauges related to reprocessing workload."""
        repo = ValuationRepository(db)
        pending_triggers = await repo.get_instrument_reprocessing_triggers_count()
        INSTRUMENT_REPROCESSING_TRIGGERS_PENDING.set(pending_triggers)

    async def _process_instrument_level_triggers(self, db):
        """
        Processes triggers from back-dated price events, creating persistent
        fan-out jobs instead of processing them in-memory.
        """
        repo = ValuationRepository(db)
        repro_job_repo = ReprocessingJobRepository(db)

        triggers = await repo.get_instrument_reprocessing_triggers(self._batch_size)
        if not triggers:
            return

        logger.info(
            f"Found {len(triggers)} instrument-level reprocessing triggers to convert to jobs."
        )

        processed_security_ids = []
        for trigger in triggers:
            payload = {
                "security_id": trigger.security_id,
                "earliest_impacted_date": trigger.earliest_impacted_date.isoformat(),
            }
            await repro_job_repo.create_job(job_type="RESET_WATERMARKS", payload=payload)
            processed_security_ids.append(trigger.security_id)

        if processed_security_ids:
            await repo.delete_instrument_reprocessing_triggers(processed_security_ids)
            logger.info(
                f"Consumed and deleted {len(processed_security_ids)} instrument-level triggers."
            )

    async def _advance_watermarks(self, db):
        """
        Checks all lagging keys, finds how far their snapshots are contiguous,
        and updates their watermark and status accordingly.
        """
        repo = ValuationRepository(db)
        position_state_repo = PositionStateRepository(db)

        latest_business_date = await repo.get_latest_business_date()
        if not latest_business_date:
            return

        lagging_states = await repo.get_lagging_states(latest_business_date, self._batch_size)

        reprocessing_count = sum(1 for s in lagging_states if s.status == "REPROCESSING")
        REPROCESSING_ACTIVE_KEYS_TOTAL.set(reprocessing_count)

        if not lagging_states:
            return

        advancable_dates = await repo.find_contiguous_snapshot_dates(lagging_states)

        updates_to_commit: List[Dict[str, Any]] = []
        for state in lagging_states:
            key = (state.portfolio_id, state.security_id)
            new_watermark = advancable_dates.get(key)

            if new_watermark and new_watermark > state.watermark_date:
                is_complete = new_watermark == latest_business_date
                new_status = "CURRENT" if is_complete else state.status
                updates_to_commit.append(
                    {
                        "portfolio_id": state.portfolio_id,
                        "security_id": state.security_id,
                        "expected_epoch": state.epoch,
                        "watermark_date": new_watermark,
                        "status": new_status,
                    }
                )

        if updates_to_commit:
            updated_count = await position_state_repo.bulk_update_states(updates_to_commit)
            log_examples = [
                f"({u['portfolio_id']},{u['security_id']})->{u['watermark_date']}"
                for u in updates_to_commit[:3]
            ]
            if updated_count != len(updates_to_commit):
                logger.warning(
                    "ValuationScheduler advanced fewer watermarks than prepared updates.",
                    extra={
                        "prepared_count": len(updates_to_commit),
                        "updated_count": updated_count,
                        "stale_skipped_count": len(updates_to_commit) - updated_count,
                        "examples": log_examples,
                    },
                )
            else:
                logger.info(
                    f"ValuationScheduler: advanced {updated_count} watermarks.",
                    extra={"examples": log_examples},
                )

    async def _create_backfill_jobs(self, db):
        """
        Finds keys with a lagging watermark and creates valuation jobs to fill the gap,
        starting from the later of the watermark date or the position's first open date.
        """
        repo = ValuationRepository(db)
        job_repo = ValuationJobRepository(db)

        latest_business_date = await repo.get_latest_business_date()

        if not latest_business_date:
            logger.debug("Scheduler: No business dates found, skipping backfill job creation.")
            return

        states_to_backfill = await repo.get_states_needing_backfill(
            latest_business_date, self._batch_size
        )

        if not states_to_backfill:
            logger.debug("Scheduler: No keys need backfilling.")
            return

        logger.info(
            "Scheduler: Found "
            f"{len(states_to_backfill)} keys needing backfill "
            f"up to {latest_business_date}."
        )

        keys_to_check = [(s.portfolio_id, s.security_id, s.epoch) for s in states_to_backfill]

        first_open_dates = await repo.get_first_open_dates_for_keys(keys_to_check)

        for state in states_to_backfill:
            gap_days = (latest_business_date - state.watermark_date).days
            SCHEDULER_GAP_DAYS.observe(gap_days)
            SNAPSHOT_LAG_SECONDS.observe(gap_days * 86400)

            POSITION_STATE_WATERMARK_LAG_DAYS.labels(
                portfolio_id=state.portfolio_id, security_id=state.security_id
            ).set(gap_days)

            key = (state.portfolio_id, state.security_id, state.epoch)
            first_open_date = first_open_dates.get(key)

            if not first_open_date:
                logger.warning(
                    f"No position history found for key {key}. Skipping backfill job creation."
                )
                continue

            start_date = max(state.watermark_date, first_open_date - timedelta(days=1))

            job_count = 0
            current_date = start_date + timedelta(days=1)

            while current_date <= latest_business_date:
                await job_repo.upsert_job(
                    portfolio_id=state.portfolio_id,
                    security_id=state.security_id,
                    valuation_date=current_date,
                    epoch=state.epoch,
                    correlation_id=f"SCHEDULER_BACKFILL_{current_date.isoformat()}",
                )
                job_count += 1
                current_date += timedelta(days=1)

            if job_count > 0:
                VALUATION_JOBS_CREATED_TOTAL.labels(
                    portfolio_id=state.portfolio_id, security_id=state.security_id
                ).inc(job_count)
                logger.info(
                    "Scheduler: Created "
                    f"{job_count} backfill valuation jobs for "
                    f"{state.security_id} in {state.portfolio_id} "
                    f"for epoch {state.epoch}."
                )

    async def _dispatch_jobs(self, jobs: List[PortfolioValuationJob]):
        """Publishes a batch of claimed jobs to Kafka."""

        if not jobs:
            return

        logger.info(f"Dispatching {len(jobs)} claimed valuation jobs to Kafka.")
        for job in jobs:
            event = PortfolioValuationRequiredEvent(
                portfolio_id=job.portfolio_id,
                security_id=job.security_id,
                valuation_date=job.valuation_date,
                epoch=job.epoch,
                correlation_id=job.correlation_id,
            )
            headers = [("correlation_id", (job.correlation_id or "").encode("utf-8"))]
            self._producer.publish_message(
                topic=KAFKA_VALUATION_REQUIRED_TOPIC,
                key=job.portfolio_id,
                value=event.model_dump(mode="json"),
                headers=headers,
            )
        self._producer.flush(timeout=10)
        logger.info(f"Successfully flushed {len(jobs)} valuation jobs.")

    async def run(self):
        """The main polling loop for the scheduler."""
        logger.info(f"ValuationScheduler started. Polling every {self._poll_interval} seconds.")
        while self._running:
            try:
                async for db in get_async_db_session():
                    async with db.begin():
                        await self._update_reprocessing_metrics(db)

                async for db in get_async_db_session():
                    async with db.begin():
                        await self._process_instrument_level_triggers(db)

                async for db in get_async_db_session():
                    async with db.begin():
                        repo = ValuationRepository(db)
                        await repo.find_and_reset_stale_jobs()

                async for db in get_async_db_session():
                    async with db.begin():
                        await self._create_backfill_jobs(db)

                for _ in range(self._dispatch_rounds_per_poll):
                    claimed_jobs = []
                    async for db in get_async_db_session():
                        async with db.begin():
                            repo = ValuationRepository(db)
                            claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
                    if not claimed_jobs:
                        break
                    await self._dispatch_jobs(claimed_jobs)

                async for db in get_async_db_session():
                    async with db.begin():
                        await self._advance_watermarks(db)

            except Exception:
                logger.error("Error in scheduler polling loop.", exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

        logger.info("ValuationScheduler has stopped.")
