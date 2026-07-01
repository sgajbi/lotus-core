# src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List

from portfolio_common.database_models import PortfolioValuationJob
from portfolio_common.db import get_async_db_session
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import (
    INSTRUMENT_REPROCESSING_TRIGGERS_PENDING,
    POSITION_STATE_WATERMARK_LAG_DAYS,
    REPROCESSING_ACTIVE_KEYS_TOTAL,
    SCHEDULER_GAP_DAYS,
    SNAPSHOT_LAG_SECONDS,
    VALUATION_JOBS_CREATED_TOTAL,
    observe_reprocessing_stale_skips,
    set_control_queue_failed_stored,
    set_control_queue_oldest_pending_age_seconds,
    set_control_queue_pending,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from portfolio_common.scheduler_dispatch_recovery import (
    DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
    DISPATCH_PUBLISH_FAILURE_PHASE,
    SchedulerDispatchError,
    dispatch_failure_reason,
    present_job_ids,
)
from portfolio_common.valuation_job_repository import ValuationJobRepository, ValuationJobUpsert

from ..repositories.valuation_repository import ValuationRepository
from ..settings import get_valuation_runtime_settings
from .valuation_job_publisher import ValuationJobPublisher, get_valuation_job_publisher

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
    ):
        runtime_settings = get_valuation_runtime_settings(
            scheduler_poll_interval_default=poll_interval,
            scheduler_batch_size_default=batch_size,
            scheduler_dispatch_rounds_default=10,
        )
        self._poll_interval = runtime_settings.valuation_scheduler_poll_interval_seconds
        self._batch_size = runtime_settings.valuation_scheduler_batch_size
        self._dispatch_rounds_per_poll = runtime_settings.valuation_scheduler_dispatch_rounds
        self._stale_timeout_minutes = runtime_settings.valuation_scheduler_stale_timeout_minutes
        self._max_attempts = runtime_settings.valuation_scheduler_max_attempts
        self._running = True
        self._stop_event = asyncio.Event()
        self._valuation_job_publisher = (
            valuation_job_publisher
            if valuation_job_publisher is not None
            else get_valuation_job_publisher()
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

    @staticmethod
    def _build_backfill_correlation_id(
        portfolio_id: str,
        security_id: str,
        epoch: int,
        valuation_date,
        watermark_updated_at: datetime | None = None,
    ) -> str:
        base_correlation_id = (
            f"SCHEDULER_BACKFILL:{portfolio_id}:{security_id}:{epoch}:{valuation_date.isoformat()}"
        )
        if watermark_updated_at is None:
            return base_correlation_id
        return f"{base_correlation_id}:{watermark_updated_at.isoformat()}"

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

        updated_count = await position_state_repo.bulk_update_states(updates)
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

    def _partition_states_without_position_history(
        self,
        states_to_backfill,
        first_open_dates: Dict[tuple[str, str, int], Any],
    ) -> tuple[list[Any], list[Any]]:
        states_to_normalize: list[Any] = []
        states_waiting_for_history: list[Any] = []

        for state in states_to_backfill:
            key = (state.portfolio_id, state.security_id, state.epoch)
            if key in first_open_dates:
                continue
            if state.status == "REPROCESSING":
                states_waiting_for_history.append(state)
            else:
                states_to_normalize.append(state)

        return states_to_normalize, states_waiting_for_history

    def _build_no_history_normalization_updates(
        self,
        states_to_normalize,
        latest_business_date,
    ) -> List[Dict[str, Any]]:
        return [
            {
                "portfolio_id": state.portfolio_id,
                "security_id": state.security_id,
                "expected_epoch": state.epoch,
                "watermark_date": latest_business_date,
                "status": "CURRENT",
            }
            for state in states_to_normalize
        ]

    async def _normalize_no_history_states(
        self,
        position_state_repo: PositionStateRepository,
        states_to_normalize,
        latest_business_date,
    ) -> None:
        normalized_updates = self._build_no_history_normalization_updates(
            states_to_normalize, latest_business_date
        )
        if not normalized_updates:
            return

        normalized_count = await position_state_repo.bulk_update_states(normalized_updates)
        stale_skipped_count = len(normalized_updates) - normalized_count
        if stale_skipped_count:
            logger.warning(
                "ValuationScheduler normalized fewer no-history states than prepared updates.",
                extra=operation_log_extra(
                    event_name="valuation.scheduler.no_history_normalization_partial",
                    operation="valuation.scheduler.create_backfill_jobs",
                    status="partial",
                    reason_code="no_history_ownership_lost",
                    prepared_count=len(normalized_updates),
                    updated_count=normalized_count,
                    stale_skipped_count=stale_skipped_count,
                ),
            )
        elif normalized_count:
            logger.info(
                "ValuationScheduler normalized no-history states to current watermark.",
                extra=operation_log_extra(
                    event_name="valuation.scheduler.no_history_normalization_completed",
                    operation="valuation.scheduler.create_backfill_jobs",
                    status="succeeded",
                    reason_code="no_history_normalized",
                    normalized_count=normalized_count,
                ),
            )

    def _log_no_history_reprocessing_defer(self, states_waiting_for_history) -> None:
        if not states_waiting_for_history:
            return

        logger.info(
            "ValuationScheduler deferred no-history reprocessing states until "
            "current-epoch position history is visible.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.no_history_deferred",
                operation="valuation.scheduler.create_backfill_jobs",
                status="deferred",
                reason_code="current_epoch_history_missing",
                deferred_count=len(states_waiting_for_history),
            ),
        )

    def _observe_backfill_gap_metrics(self, state, latest_business_date) -> None:
        gap_days = (latest_business_date - state.watermark_date).days
        SCHEDULER_GAP_DAYS.observe(gap_days)
        SNAPSHOT_LAG_SECONDS.observe(gap_days * 86400)
        POSITION_STATE_WATERMARK_LAG_DAYS.set(gap_days)

    def _log_missing_current_epoch_history(self, state, latest_business_date) -> None:
        logger.info(
            "No current-epoch position history found; skipping backfill for now.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.current_epoch_history_missing",
                operation="valuation.scheduler.create_backfill_jobs",
                status="skipped",
                reason_code="current_epoch_history_missing",
                epoch=state.epoch,
                state_status=state.status,
                latest_business_date=str(latest_business_date),
            ),
        )

    def _build_backfill_job_requests(
        self,
        state,
        first_open_date,
        latest_business_date,
    ) -> list[ValuationJobUpsert]:
        start_date = max(state.watermark_date, first_open_date - timedelta(days=1))
        job_requests: list[ValuationJobUpsert] = []
        current_date = start_date + timedelta(days=1)

        while current_date <= latest_business_date:
            job_requests.append(
                ValuationJobUpsert(
                    portfolio_id=state.portfolio_id,
                    security_id=state.security_id,
                    valuation_date=current_date,
                    epoch=state.epoch,
                    correlation_id=self._build_backfill_correlation_id(
                        state.portfolio_id,
                        state.security_id,
                        state.epoch,
                        current_date,
                        state.updated_at,
                    ),
                )
            )
            current_date += timedelta(days=1)

        return job_requests

    async def _stage_backfill_jobs_for_state(
        self,
        job_repo: ValuationJobRepository,
        state,
        first_open_date,
        latest_business_date,
    ) -> None:
        job_requests = self._build_backfill_job_requests(
            state, first_open_date, latest_business_date
        )
        if not job_requests:
            return

        staged_count = await job_repo.upsert_jobs(job_requests)
        VALUATION_JOBS_CREATED_TOTAL.labels(job_type="backfill").inc(staged_count)
        logger.info(
            "Backfill valuation jobs staged.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.backfill_jobs_staged",
                operation="valuation.scheduler.create_backfill_jobs",
                status="succeeded",
                reason_code="jobs_staged",
                staged_count=staged_count,
                requested_count=len(job_requests),
                epoch=state.epoch,
            ),
        )

    async def _process_backfill_states(
        self,
        job_repo: ValuationJobRepository,
        states_to_backfill,
        first_open_dates: Dict[tuple[str, str, int], Any],
        latest_business_date,
    ) -> None:
        for state in states_to_backfill:
            self._observe_backfill_gap_metrics(state, latest_business_date)
            key = (state.portfolio_id, state.security_id, state.epoch)
            first_open_date = first_open_dates.get(key)

            if not first_open_date:
                self._log_missing_current_epoch_history(state, latest_business_date)
                continue

            await self._stage_backfill_jobs_for_state(
                job_repo, state, first_open_date, latest_business_date
            )

    async def _create_backfill_jobs(self, db):
        """
        Finds keys with a lagging watermark and creates valuation jobs to fill the gap,
        starting from the later of the watermark date or the position's first open date.
        """
        repo = ValuationRepository(db)
        job_repo = ValuationJobRepository(db)
        position_state_repo = PositionStateRepository(db)

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
            "Valuation states needing backfill found.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.backfill_states_found",
                operation="valuation.scheduler.create_backfill_jobs",
                status="started",
                reason_code="backfill_states_found",
                state_count=len(states_to_backfill),
                latest_business_date=str(latest_business_date),
            ),
        )

        keys_to_check = [(s.portfolio_id, s.security_id, s.epoch) for s in states_to_backfill]

        first_open_dates = await repo.get_first_open_dates_for_keys(keys_to_check)
        (
            keys_without_history_to_normalize,
            keys_waiting_for_history,
        ) = self._partition_states_without_position_history(states_to_backfill, first_open_dates)
        await self._normalize_no_history_states(
            position_state_repo,
            keys_without_history_to_normalize,
            latest_business_date,
        )
        self._log_no_history_reprocessing_defer(keys_waiting_for_history)
        await self._process_backfill_states(
            job_repo,
            states_to_backfill,
            first_open_dates,
            latest_business_date,
        )

    def _valuation_job_record_key(self, job: PortfolioValuationJob) -> str:
        return f"{job.portfolio_id}|{job.security_id}|{job.valuation_date.isoformat()}|{job.epoch}"

    def _valuation_job_headers(self, job: PortfolioValuationJob) -> list[tuple[str, bytes]]:
        if not job.correlation_id:
            return []
        return [("correlation_id", job.correlation_id.encode("utf-8"))]

    def _valuation_required_event(self, job: PortfolioValuationJob) -> dict[str, Any]:
        event = PortfolioValuationRequiredEvent(
            portfolio_id=job.portfolio_id,
            security_id=job.security_id,
            valuation_date=job.valuation_date,
            epoch=job.epoch,
            correlation_id=job.correlation_id,
        )
        return event.model_dump(mode="json")

    def _publish_valuation_job(self, job: PortfolioValuationJob) -> None:
        self._valuation_job_publisher.publish_job_requested(
            key=job.portfolio_id,
            value=self._valuation_required_event(job),
            headers=self._valuation_job_headers(job),
        )

    def _raise_dispatch_failure(
        self,
        *,
        queued_count: int,
        published_jobs: list[PortfolioValuationJob],
        published_record_keys: list[str],
        remaining_jobs: list[PortfolioValuationJob],
        remaining_record_keys: list[str],
        cause: Exception,
    ) -> None:
        undelivered_count = self._valuation_job_publisher.confirm_delivery(timeout_seconds=10)
        if undelivered_count:
            affected_record_keys = [*published_record_keys, *remaining_record_keys]
            affected_keys = ", ".join(affected_record_keys)
            raise SchedulerDispatchError(
                message=(
                    "Delivery confirmation timed out while recovering from valuation dispatch "
                    f"failure. Affected job keys: {affected_keys}."
                ),
                recovery_job_ids=present_job_ids([*published_jobs, *remaining_jobs]),
                recovery_record_keys=tuple(affected_record_keys),
                published_record_keys=tuple(published_record_keys),
                failure_phase=DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
            ) from cause
        remaining_keys = ", ".join(remaining_record_keys)
        raise SchedulerDispatchError(
            message=(
                "Failed to dispatch valuation jobs after "
                f"{queued_count} earlier job(s) were queued. Remaining job keys: {remaining_keys}."
            ),
            recovery_job_ids=present_job_ids(remaining_jobs),
            recovery_record_keys=tuple(remaining_record_keys),
            published_record_keys=tuple(published_record_keys),
            failure_phase=DISPATCH_PUBLISH_FAILURE_PHASE,
        ) from cause

    def _confirm_dispatched_jobs(self, record_keys: list[str]) -> None:
        undelivered_count = self._valuation_job_publisher.confirm_delivery(timeout_seconds=10)
        if not undelivered_count:
            return
        affected_keys = ", ".join(record_keys)
        raise SchedulerDispatchError(
            message=(
                "Delivery confirmation timed out while dispatching valuation jobs. "
                f"Affected job keys: {affected_keys}."
            ),
            recovery_job_ids=(),
            recovery_record_keys=tuple(record_keys),
            published_record_keys=tuple(record_keys),
            failure_phase=DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
        )

    async def _dispatch_jobs(self, jobs: List[PortfolioValuationJob]):
        """Publishes a batch of claimed jobs to Kafka."""

        if not jobs:
            return

        logger.info(
            "Claimed valuation jobs dispatch started.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.dispatch_started",
                operation="valuation.scheduler.dispatch_jobs",
                status="started",
                reason_code="jobs_claimed",
                job_count=len(jobs),
            ),
        )
        record_keys = [self._valuation_job_record_key(job) for job in jobs]
        for idx, job in enumerate(jobs):
            try:
                self._publish_valuation_job(job)
            except Exception as exc:
                self._raise_dispatch_failure(
                    queued_count=idx,
                    published_jobs=jobs[:idx],
                    published_record_keys=record_keys[:idx],
                    remaining_jobs=jobs[idx:],
                    remaining_record_keys=record_keys[idx:],
                    cause=exc,
                )
        try:
            self._confirm_dispatched_jobs(record_keys)
        except SchedulerDispatchError as exc:
            raise SchedulerDispatchError(
                message=exc.message,
                recovery_job_ids=present_job_ids(jobs),
                recovery_record_keys=exc.recovery_record_keys,
                published_record_keys=exc.published_record_keys,
                failure_phase=exc.failure_phase,
            ) from exc
        logger.info(
            "Claimed valuation jobs dispatch flushed.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.dispatch_flushed",
                operation="valuation.scheduler.dispatch_jobs",
                status="succeeded",
                reason_code="producer_flush_completed",
                job_count=len(jobs),
            ),
        )

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

    async def _claim_and_dispatch_ready_jobs(self) -> None:
        for _ in range(self._dispatch_rounds_per_poll):
            claimed_jobs: list[PortfolioValuationJob] = []
            async for db in get_async_db_session():
                async with db.begin():
                    repo = ValuationRepository(db)
                    claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
            if not claimed_jobs:
                break
            try:
                await self._dispatch_jobs(claimed_jobs)
            except SchedulerDispatchError as exc:
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
        await self._run_db_poll_step(self._update_reprocessing_and_queue_metrics)
        await self._run_db_poll_step(self._process_instrument_level_triggers)
        await self._run_db_poll_step(self._reset_stale_valuation_jobs)
        await self._run_db_poll_step(self._create_backfill_jobs)
        await self._claim_and_dispatch_ready_jobs()
        await self._run_db_poll_step(self._advance_watermarks)
        await self._run_db_poll_step(self._update_queue_metrics)

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
