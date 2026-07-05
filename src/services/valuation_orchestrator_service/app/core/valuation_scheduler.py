# src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List

from portfolio_common.database_models import PortfolioValuationJob
from portfolio_common.db import get_async_db_session
from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import (
    INSTRUMENT_REPROCESSING_TRIGGERS_PENDING,
    REPROCESSING_ACTIVE_KEYS_TOTAL,
    observe_reprocessing_stale_skips,
    observe_valuation_scheduler_budget_exhausted,
    observe_valuation_scheduler_jobs_claimed,
    observe_valuation_scheduler_poll_duration,
    observe_valuation_scheduler_producer_backpressure,
    set_control_queue_failed_stored,
    set_control_queue_oldest_pending_age_seconds,
    set_control_queue_pending,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from portfolio_common.scheduler_dispatch_recovery import (
    DISPATCH_BUDGET_EXHAUSTED_PHASE,
    SchedulerDispatchError,
    dispatch_failure_reason,
)
from portfolio_common.valuation_job_repository import ValuationJobRepository

from ..repositories.valuation_repository import ValuationRepository
from ..settings import get_valuation_runtime_settings
from .valuation_backfill_planner import ValuationBackfillPlanner
from .valuation_job_dispatcher import ValuationJobDispatcher
from .valuation_job_publisher import (
    ValuationJobPublisher,
    ValuationJobPublishError,
    get_valuation_job_publisher,
)

logger = logging.getLogger(__name__)


class ValuationScheduler:
    """
    A background task that drives all valuation activity. It polls the position_state
    table to find keys that need backfilling, creates the necessary valuation jobs,
    dispatches them, and advances watermarks upon completion.
    """

    def __init__(
        self,
        poll_interval: int = 30,
        batch_size: int = 100,
        valuation_job_publisher: ValuationJobPublisher | None = None,
        valuation_job_dispatcher: ValuationJobDispatcher | None = None,
        valuation_backfill_planner: ValuationBackfillPlanner | None = None,
    ):
        runtime_settings = get_valuation_runtime_settings(
            scheduler_poll_interval_default=poll_interval,
            scheduler_batch_size_default=batch_size,
            scheduler_dispatch_rounds_default=10,
        )
        self._poll_interval = runtime_settings.valuation_scheduler_poll_interval_seconds
        self._batch_size = runtime_settings.valuation_scheduler_batch_size
        self._dispatch_rounds_per_poll = runtime_settings.valuation_scheduler_dispatch_rounds
        self._poll_budget_seconds = runtime_settings.valuation_scheduler_poll_budget_seconds
        self._dispatch_budget_seconds = runtime_settings.valuation_scheduler_dispatch_budget_seconds
        self._backfill_upsert_chunk_size = (
            runtime_settings.valuation_scheduler_backfill_upsert_chunk_size
        )
        self._stale_timeout_minutes = runtime_settings.valuation_scheduler_stale_timeout_minutes
        self._max_attempts = runtime_settings.valuation_scheduler_max_attempts
        self._running = True
        self._stop_event = asyncio.Event()
        self._valuation_job_publisher = (
            valuation_job_publisher
            if valuation_job_publisher is not None
            else get_valuation_job_publisher()
        )
        self._valuation_job_dispatcher = (
            valuation_job_dispatcher
            if valuation_job_dispatcher is not None
            else ValuationJobDispatcher(
                valuation_job_publisher=self._valuation_job_publisher,
                dispatch_budget_seconds=self._dispatch_budget_seconds,
            )
        )
        self._valuation_backfill_planner = (
            valuation_backfill_planner
            if valuation_backfill_planner is not None
            else ValuationBackfillPlanner(
                backfill_upsert_chunk_size=self._backfill_upsert_chunk_size
            )
        )

    def stop(self):
        """Signals the scheduler to gracefully shut down."""
        logger.info(
            "Valuation scheduler shutdown signal received.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.shutdown_started",
                operation="valuation.scheduler.run",
                status="stopping",
                reason_code="shutdown_requested",
            ),
        )
        self._running = False
        self._stop_event.set()

    async def _update_reprocessing_metrics(self, db):
        """Queries for and sets key gauges related to reprocessing workload."""
        repo = ValuationRepository(db)
        pending_triggers = await repo.get_instrument_reprocessing_triggers_count()
        INSTRUMENT_REPROCESSING_TRIGGERS_PENDING.set(pending_triggers)

    async def _update_queue_metrics(self, db):
        repo = ValuationRepository(db)
        queue_stats = await repo.get_job_queue_stats()
        set_control_queue_pending("valuation", queue_stats["pending_count"])
        set_control_queue_failed_stored("valuation", queue_stats["failed_count"])
        oldest_pending_created_at = queue_stats["oldest_pending_created_at"]
        if oldest_pending_created_at is None:
            set_control_queue_oldest_pending_age_seconds("valuation", 0.0)
            return
        age_seconds = (
            datetime.now(timezone.utc) - oldest_pending_created_at.astimezone(timezone.utc)
        ).total_seconds()
        set_control_queue_oldest_pending_age_seconds("valuation", max(age_seconds, 0.0))

    async def _process_instrument_level_triggers(self, db):
        """
        Processes triggers from back-dated price events, creating persistent
        fan-out jobs instead of processing them in-memory.
        """
        repo = ValuationRepository(db)
        repro_job_repo = ReprocessingJobRepository(db)

        triggers = await repo.claim_instrument_reprocessing_triggers(self._batch_size)
        if not triggers:
            return

        logger.info(
            "Instrument-level reprocessing triggers claimed.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.instrument_triggers_claimed",
                operation="valuation.scheduler.process_instrument_triggers",
                status="started",
                reason_code="triggers_claimed",
                trigger_count=len(triggers),
            ),
        )

        for trigger in triggers:
            payload = {
                "security_id": trigger.security_id,
                "earliest_impacted_date": trigger.earliest_impacted_date.isoformat(),
            }
            await repro_job_repo.create_job(
                job_type="RESET_WATERMARKS",
                payload=payload,
                correlation_id=trigger.correlation_id,
            )
        logger.info(
            "Consumed %s instrument-level triggers into durable replay jobs.",
            len(triggers),
            extra=operation_log_extra(
                event_name="valuation.scheduler.instrument_triggers_consumed",
                operation="valuation.scheduler.process_instrument_triggers",
                status="succeeded",
                reason_code="jobs_created",
                trigger_count=len(triggers),
            ),
        )

    def _build_terminal_reprocessing_updates(self, states) -> List[Dict[str, Any]]:
        return [
            {
                "portfolio_id": state.portfolio_id,
                "security_id": state.security_id,
                "expected_epoch": state.epoch,
                "watermark_date": state.watermark_date,
                "status": "CURRENT",
            }
            for state in states
        ]

    def _build_watermark_advance_updates(
        self,
        states,
        advancable_dates: Dict[tuple[str, str], Any],
        latest_business_date,
    ) -> List[Dict[str, Any]]:
        updates_to_commit: List[Dict[str, Any]] = []
        for state in states:
            key = (state.portfolio_id, state.security_id)
            new_watermark = advancable_dates.get(key)

            if new_watermark and new_watermark > state.watermark_date:
                is_complete = new_watermark == latest_business_date
                updates_to_commit.append(
                    {
                        "portfolio_id": state.portfolio_id,
                        "security_id": state.security_id,
                        "expected_epoch": state.epoch,
                        "watermark_date": new_watermark,
                        "status": "CURRENT" if is_complete else state.status,
                    }
                )
        return updates_to_commit

    async def _bulk_update_watermark_states(
        self,
        position_state_repo: PositionStateRepository,
        updates: List[Dict[str, Any]],
        *,
        stale_skip_reason: str,
        warning_message: str,
        success_message: str,
        success_extra_key: str,
    ) -> int:
        if not updates:
            return 0

        updated_count = int(await position_state_repo.bulk_update_states(updates))
        stale_skipped_count = len(updates) - updated_count

        if stale_skipped_count:
            observe_reprocessing_stale_skips(stale_skip_reason, stale_skipped_count)
            logger.warning(
                warning_message,
                extra=operation_log_extra(
                    event_name="valuation.scheduler.watermark_bulk_update_partial",
                    operation="valuation.scheduler.advance_watermarks",
                    status="partial",
                    reason_code=stale_skip_reason,
                    prepared_count=len(updates),
                    updated_count=updated_count,
                    stale_skipped_count=stale_skipped_count,
                ),
            )
        elif updated_count:
            logger.info(
                success_message,
                extra=operation_log_extra(
                    event_name="valuation.scheduler.watermark_bulk_update_completed",
                    operation="valuation.scheduler.advance_watermarks",
                    status="succeeded",
                    reason_code="watermark_update_completed",
                    **{success_extra_key: updated_count},
                ),
            )

        return updated_count

    async def _normalize_terminal_reprocessing_states(
        self,
        position_state_repo: PositionStateRepository,
        terminal_reprocessing_states,
    ) -> None:
        terminal_updates = self._build_terminal_reprocessing_updates(terminal_reprocessing_states)
        await self._bulk_update_watermark_states(
            position_state_repo,
            terminal_updates,
            stale_skip_reason="terminal_reprocessing_normalization",
            warning_message=(
                "ValuationScheduler normalized fewer terminal reprocessing states than "
                "prepared updates."
            ),
            success_message="ValuationScheduler normalized terminal reprocessing states.",
            success_extra_key="normalized_count",
        )

    async def _advance_lagging_watermark_states(
        self,
        repo: ValuationRepository,
        position_state_repo: PositionStateRepository,
        *,
        lagging_states,
        first_open_dates,
        latest_business_date,
    ) -> None:
        advancable_dates = await repo.find_contiguous_snapshot_dates(
            lagging_states, first_open_dates
        )
        updates_to_commit = self._build_watermark_advance_updates(
            lagging_states,
            advancable_dates,
            latest_business_date,
        )
        await self._bulk_update_watermark_states(
            position_state_repo,
            updates_to_commit,
            stale_skip_reason="watermark_advance",
            warning_message="ValuationScheduler advanced fewer watermarks than prepared updates.",
            success_message="ValuationScheduler advanced watermarks.",
            success_extra_key="updated_count",
        )

    async def _load_watermark_advance_inputs(
        self, repo: ValuationRepository
    ) -> tuple[Any, list[Any], list[Any], Dict[tuple[str, str, int], Any]] | None:
        latest_business_date = await repo.get_latest_business_date()
        if not latest_business_date:
            return None

        lagging_states = await repo.get_lagging_states(latest_business_date, self._batch_size)
        terminal_reprocessing_states = await repo.get_terminal_reprocessing_states(
            latest_business_date, self._batch_size
        )
        lagging_keys = [(s.portfolio_id, s.security_id, s.epoch) for s in lagging_states]
        first_open_dates = await repo.get_first_open_dates_for_keys(lagging_keys)
        return (
            latest_business_date,
            lagging_states,
            terminal_reprocessing_states,
            first_open_dates,
        )

    def _observe_reprocessing_active_keys(
        self,
        lagging_states,
        terminal_reprocessing_states,
    ) -> None:
        reprocessing_count = sum(1 for s in lagging_states if s.status == "REPROCESSING") + len(
            terminal_reprocessing_states
        )
        REPROCESSING_ACTIVE_KEYS_TOTAL.set(reprocessing_count)

    async def _advance_watermarks(self, db):
        """
        Checks all lagging keys, finds how far their snapshots are contiguous,
        and updates their watermark and status accordingly.
        """
        repo = ValuationRepository(db)
        position_state_repo = PositionStateRepository(db)

        inputs = await self._load_watermark_advance_inputs(repo)
        if inputs is None:
            return
        (
            latest_business_date,
            lagging_states,
            terminal_reprocessing_states,
            first_open_dates,
        ) = inputs
        self._observe_reprocessing_active_keys(
            lagging_states,
            terminal_reprocessing_states,
        )

        await self._normalize_terminal_reprocessing_states(
            position_state_repo, terminal_reprocessing_states
        )

        if lagging_states:
            await self._advance_lagging_watermark_states(
                repo,
                position_state_repo,
                lagging_states=lagging_states,
                first_open_dates=first_open_dates,
                latest_business_date=latest_business_date,
            )

    async def _create_backfill_jobs(self, db):
        """
        Finds keys with a lagging watermark and creates valuation jobs to fill the gap,
        starting from the later of the watermark date or the position's first open date.
        """
        repo = ValuationRepository(db)
        job_repo = ValuationJobRepository(db)
        position_state_repo = PositionStateRepository(db)
        await self._valuation_backfill_planner.create_backfill_jobs(
            repo=repo,
            job_repo=job_repo,
            position_state_repo=position_state_repo,
            batch_size=self._batch_size,
        )

    @staticmethod
    def _budget_exhausted(*, started_at: float, budget_seconds: int) -> bool:
        return time.monotonic() - started_at >= budget_seconds

    async def _dispatch_jobs(self, jobs: List[PortfolioValuationJob]):
        await self._valuation_job_dispatcher.dispatch_jobs(jobs)

    async def _recover_dispatch_failure(self, failure: SchedulerDispatchError) -> None:
        if not failure.recovery_job_ids:
            logger.warning(
                "Valuation scheduler dispatch failure had no durable job ids to recover.",
                extra=operation_log_extra(
                    event_name="valuation.scheduler.dispatch_recovery_skipped",
                    operation="valuation.scheduler.dispatch_jobs",
                    status="skipped",
                    reason_code="missing_recovery_job_ids",
                    failure_phase=failure.failure_phase,
                    recovery_record_count=len(failure.recovery_record_keys),
                    published_record_count=len(failure.published_record_keys),
                ),
            )
            return
        async for db in get_async_db_session():
            async with db.begin():
                repo = ValuationRepository(db)
                await repo.recover_dispatch_failed_jobs(
                    list(failure.recovery_job_ids),
                    max_attempts=self._max_attempts,
                    failure_reason=dispatch_failure_reason(
                        failure_phase=failure.failure_phase,
                        record_keys=failure.recovery_record_keys,
                    ),
                )

    def _observe_dispatch_stop(self, failure: SchedulerDispatchError) -> None:
        if failure.failure_phase == DISPATCH_BUDGET_EXHAUSTED_PHASE:
            observe_valuation_scheduler_budget_exhausted("dispatch")
            return
        cause = failure.__cause__
        if (
            isinstance(cause, ValuationJobPublishError)
            and cause.reason_code == "kafka_publish_back_pressure"
        ):
            observe_valuation_scheduler_producer_backpressure()

    async def _claim_and_dispatch_ready_jobs(self) -> None:
        poll_started_at = time.monotonic()
        for _ in range(self._dispatch_rounds_per_poll):
            if self._budget_exhausted(
                started_at=poll_started_at,
                budget_seconds=self._poll_budget_seconds,
            ):
                observe_valuation_scheduler_budget_exhausted("poll")
                logger.info(
                    "Valuation scheduler poll budget exhausted before next dispatch round.",
                    extra=operation_log_extra(
                        event_name="valuation.scheduler.poll_budget_exhausted",
                        operation="valuation.scheduler.claim_and_dispatch",
                        status="deferred",
                        reason_code="poll_budget_exhausted",
                        poll_budget_seconds=self._poll_budget_seconds,
                    ),
                )
                break
            claimed_jobs: list[PortfolioValuationJob] = []
            async for db in get_async_db_session():
                async with db.begin():
                    repo = ValuationRepository(db)
                    claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
            if not claimed_jobs:
                break
            observe_valuation_scheduler_jobs_claimed(len(claimed_jobs))
            try:
                await self._dispatch_jobs(claimed_jobs)
            except SchedulerDispatchError as exc:
                self._observe_dispatch_stop(exc)
                await self._recover_dispatch_failure(exc)
                raise
            if len(claimed_jobs) < self._batch_size:
                break

    async def _run_db_poll_step(self, step: Callable[[Any], Awaitable[None]]) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                await step(db)

    async def _update_reprocessing_and_queue_metrics(self, db) -> None:
        await self._update_reprocessing_metrics(db)
        await self._update_queue_metrics(db)

    async def _reset_stale_valuation_jobs(self, db) -> None:
        repo = ValuationRepository(db)
        await repo.find_and_reset_stale_jobs(
            timeout_minutes=self._stale_timeout_minutes,
            max_attempts=self._max_attempts,
        )

    async def _run_poll_once(self) -> None:
        poll_started_at = time.monotonic()
        try:
            await self._run_db_poll_step(self._update_reprocessing_and_queue_metrics)
            await self._run_db_poll_step(self._process_instrument_level_triggers)
            await self._run_db_poll_step(self._reset_stale_valuation_jobs)
            await self._run_db_poll_step(self._create_backfill_jobs)
            await self._claim_and_dispatch_ready_jobs()
            await self._run_db_poll_step(self._advance_watermarks)
            await self._run_db_poll_step(self._update_queue_metrics)
        finally:
            observe_valuation_scheduler_poll_duration(time.monotonic() - poll_started_at)

    async def _wait_for_next_poll_or_stop(self) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
            return False
        except asyncio.TimeoutError:
            return True
        except asyncio.CancelledError:
            return False

    async def run(self):
        """The main polling loop for the scheduler."""
        logger.info(
            "Valuation scheduler started.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.started",
                operation="valuation.scheduler.run",
                status="running",
                reason_code="poll_loop_started",
                poll_interval_seconds=self._poll_interval,
            ),
        )
        while self._running:
            try:
                await self._run_poll_once()
            except Exception:
                logger.error(
                    "Valuation scheduler polling loop failed.",
                    exc_info=True,
                    extra=operation_log_extra(
                        event_name="valuation.scheduler.poll_loop_failed",
                        operation="valuation.scheduler.run",
                        status="failed",
                        reason_code="poll_loop_error",
                    ),
                )

            if not await self._wait_for_next_poll_or_stop():
                break

        logger.info(
            "Valuation scheduler stopped.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.stopped",
                operation="valuation.scheduler.run",
                status="stopped",
                reason_code="poll_loop_stopped",
            ),
        )
