# src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py
import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

from portfolio_common.db import get_async_db_session
from portfolio_common.logging_utils import correlation_id_var, operation_log_extra
from portfolio_common.monitoring import (
    observe_reprocessing_stale_skips,
    observe_reprocessing_worker_jobs_claimed,
    observe_reprocessing_worker_jobs_completed,
    observe_reprocessing_worker_jobs_failed,
    observe_reprocessing_worker_jobs_noop,
    observe_reprocessing_worker_lease_renewal,
    reprocessing_worker_batch_timer,
    set_control_queue_failed_stored,
    set_control_queue_oldest_pending_age_seconds,
    set_control_queue_pending,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import (
    ReprocessingJobRepository,
    ReprocessingJobTransitionOutcome,
)
from portfolio_common.runtime_settings import RuntimeConfigurationError

from ..domain.fx_revaluation import FX_REVALUATION_JOB_TYPE
from ..infrastructure.repositories.fx_revaluation_repository import (
    SqlAlchemyFxRevaluationRepository,
)
from ..repositories.valuation_repository import ValuationRepository
from ..settings import get_valuation_runtime_settings
from .fx_revaluation_job_processor import (
    FxRevaluationJobOwnershipLostError,
    FxRevaluationJobProcessor,
)
from .reprocessing_failure import reprocessing_failure_reason
from .reprocessing_worker_dependencies import ReprocessingWorkerRepositoryFactory

logger = logging.getLogger(__name__)


def _validate_lease_renewal_timing(
    *,
    io_timeout_seconds: float,
    interval_seconds: float,
    lease_duration_seconds: float,
) -> None:
    if not 0 < io_timeout_seconds < interval_seconds < lease_duration_seconds:
        raise RuntimeConfigurationError(
            "Invalid reprocessing lease renewal timing: require I/O timeout < interval < lease"
        )


class ReprocessingJobOwnershipLostError(RuntimeError):
    """Abort a job transaction when its durable lease no longer authorizes completion."""


def _reset_watermark_job_scope(job) -> tuple[str, date, date]:
    security_id = job.payload["security_id"]
    earliest_date = date.fromisoformat(job.payload["earliest_impacted_date"])
    new_watermark = earliest_date - timedelta(days=1)
    return security_id, earliest_date, new_watermark


def _record_reset_watermark_fanout(
    job,
    security_id: str,
    affected_portfolios: list[str],
    updated_count: int,
) -> None:
    targeted_count = len(affected_portfolios)
    if updated_count == targeted_count:
        logger.info(
            "Reprocessing watermark reset fanout completed.",
            extra=operation_log_extra(
                event_name="valuation.reprocessing.watermark_fanout_completed",
                operation="valuation.reprocessing.reset_watermarks",
                status="succeeded",
                reason_code="fanout_completed",
                job_id=job.id,
                targeted_count=targeted_count,
                updated_count=updated_count,
            ),
        )
        return

    stale_skipped_count = targeted_count - updated_count
    observe_reprocessing_stale_skips("reset_watermarks_fanout", stale_skipped_count)
    logger.warning(
        "Reprocessing watermark reset fanout updated fewer rows than targeted.",
        extra=operation_log_extra(
            event_name="valuation.reprocessing.watermark_fanout_partial",
            operation="valuation.reprocessing.reset_watermarks",
            status="partial",
            reason_code="stale_watermark_rows",
            job_id=job.id,
            targeted_count=targeted_count,
            updated_count=updated_count,
            stale_skipped_count=stale_skipped_count,
        ),
    )


class ReprocessingWorker:
    """
    A background worker that polls for and processes durable reprocessing jobs.
    """

    def __init__(
        self,
        poll_interval: int = 10,
        batch_size: int = 10,
        fx_job_processor: FxRevaluationJobProcessor | None = None,
        session_provider: Callable[[], AsyncIterator[Any]] | None = None,
        repository_factory: ReprocessingWorkerRepositoryFactory | None = None,
    ):
        runtime_settings = get_valuation_runtime_settings(
            worker_poll_interval_default=poll_interval,
            worker_batch_size_default=batch_size,
        )
        self._poll_interval = runtime_settings.reprocessing_worker_poll_interval_seconds
        self._batch_size = runtime_settings.reprocessing_worker_batch_size
        self._stale_timeout_minutes = runtime_settings.reprocessing_worker_stale_timeout_minutes
        self._lease_duration_seconds = self._stale_timeout_minutes * 60
        self._lease_renewal_interval_seconds = max(1.0, self._lease_duration_seconds / 3)
        self._lease_renewal_io_timeout_seconds = self._lease_renewal_interval_seconds / 2
        _validate_lease_renewal_timing(
            io_timeout_seconds=self._lease_renewal_io_timeout_seconds,
            interval_seconds=self._lease_renewal_interval_seconds,
            lease_duration_seconds=self._lease_duration_seconds,
        )
        self._lease_owner = f"valuation-reprocessing-{uuid.uuid4().hex}"
        self._max_attempts = runtime_settings.reprocessing_worker_max_attempts
        self._running = True
        self._stop_event = asyncio.Event()
        self._fx_job_processor = fx_job_processor or FxRevaluationJobProcessor(
            no_impact_attempt_limit=self._max_attempts
        )
        self._session_provider = session_provider
        self._repository_factory = repository_factory or ReprocessingWorkerRepositoryFactory(
            reprocessing_job_repository_factory=lambda db: ReprocessingJobRepository(db),
            position_state_repository_factory=lambda db: PositionStateRepository(db),
            valuation_repository_factory=lambda db: ValuationRepository(db),
            fx_revaluation_repository_factory=lambda db: SqlAlchemyFxRevaluationRepository(db),
        )

    def _open_session(self) -> AsyncIterator[Any]:
        if self._session_provider is not None:
            return cast(AsyncIterator[Any], self._session_provider())
        return cast(AsyncIterator[Any], get_async_db_session())

    def stop(self):
        logger.info(
            "Reprocessing worker shutdown signal received.",
            extra=operation_log_extra(
                event_name="valuation.reprocessing_worker.shutdown_started",
                operation="valuation.reprocessing_worker.run",
                status="stopping",
                reason_code="shutdown_requested",
            ),
        )
        self._running = False
        self._stop_event.set()

    async def _update_queue_metrics(self, job_repo: ReprocessingJobRepository):
        queue_stats = await job_repo.get_queue_stats()
        set_control_queue_pending("reprocessing", queue_stats["pending_count"])
        set_control_queue_failed_stored("reprocessing", queue_stats["failed_count"])
        oldest_pending_created_at = queue_stats["oldest_pending_created_at"]
        if oldest_pending_created_at is None:
            set_control_queue_oldest_pending_age_seconds("reprocessing", 0.0)
            return
        age_seconds = (
            datetime.now(timezone.utc) - oldest_pending_created_at.astimezone(timezone.utc)
        ).total_seconds()
        set_control_queue_oldest_pending_age_seconds("reprocessing", max(age_seconds, 0.0))

    async def _process_batch(self):
        """Claim each job immediately before its independently committed execution."""
        with reprocessing_worker_batch_timer():
            await self._recover_stale_jobs()
            processed_reset_job_ids: set[int] = set()
            for _ in range(self._batch_size):
                job = await self._claim_next_reset_watermark_job(
                    excluded_job_ids=tuple(sorted(processed_reset_job_ids)),
                    normalize_reset_watermark_duplicates=not processed_reset_job_ids,
                )
                if job is None:
                    break
                processed_reset_job_ids.add(job.id)
                await self._process_reset_watermark_job(job=job)

            processed_fx_job_ids: set[int] = set()
            for _ in range(self._batch_size):
                job = await self._claim_next_fx_revaluation_job(
                    excluded_job_ids=tuple(sorted(processed_fx_job_ids))
                )
                if job is None:
                    break
                processed_fx_job_ids.add(job.job_id)
                await self._process_fx_revaluation_job(job=job)

            await self._refresh_queue_metrics()

    async def _recover_stale_jobs(self) -> None:
        async for db in self._open_session():
            async with db.begin():
                await self._repository_factory.reprocessing_jobs(db).find_and_reset_stale_jobs(
                    max_attempts=self._max_attempts
                )

    async def _claim_next_reset_watermark_job(
        self,
        *,
        excluded_job_ids: tuple[int, ...],
        normalize_reset_watermark_duplicates: bool,
    ) -> Any | None:
        claimed_jobs = []
        async for db in self._open_session():
            async with db.begin():
                claimed_jobs = await self._repository_factory.reprocessing_jobs(
                    db
                ).find_and_claim_jobs(
                    "RESET_WATERMARKS",
                    1,
                    lease_owner=self._lease_owner,
                    lease_duration_seconds=self._lease_duration_seconds,
                    excluded_job_ids=excluded_job_ids,
                    normalize_reset_watermark_duplicates=(normalize_reset_watermark_duplicates),
                )
        if claimed_jobs:
            observe_reprocessing_worker_jobs_claimed("RESET_WATERMARKS", 1)
            return claimed_jobs[0]
        return None

    async def _claim_next_fx_revaluation_job(
        self, *, excluded_job_ids: tuple[int, ...]
    ) -> Any | None:
        claimed_jobs = []
        async for db in self._open_session():
            async with db.begin():
                repository = self._repository_factory.fx_revaluations(db)
                claimed_jobs = await repository.claim_pending_jobs(
                    1,
                    lease_owner=self._lease_owner,
                    lease_duration_seconds=self._lease_duration_seconds,
                    excluded_job_ids=excluded_job_ids,
                )
        if claimed_jobs:
            observe_reprocessing_worker_jobs_claimed(FX_REVALUATION_JOB_TYPE, 1)
            return claimed_jobs[0]
        return None

    async def _refresh_queue_metrics(self) -> None:
        async for db in self._open_session():
            async with db.begin():
                await self._update_queue_metrics(self._repository_factory.reprocessing_jobs(db))

    async def _process_reset_watermark_job(
        self,
        *,
        job,
    ) -> None:
        correlation_token = None
        try:
            if job.correlation_id:
                correlation_token = correlation_id_var.set(job.correlation_id)
            await self._process_with_lease_renewal(
                job=job,
                job_type="RESET_WATERMARKS",
                operation=lambda terminal_started: self._execute_reset_watermark_job(
                    job,
                    terminal_started,
                ),
            )
        except ReprocessingJobOwnershipLostError:
            pass
        except Exception as exc:
            await self._mark_reset_watermark_job_failed(job=job, exc=exc)
        finally:
            if correlation_token is not None:
                correlation_id_var.reset(correlation_token)

    async def _execute_reset_watermark_job(
        self,
        job,
        terminal_transition_started: asyncio.Event,
    ) -> None:
        async for db in self._open_session():
            async with db.begin():
                should_complete_job, _security_id = await self._reset_impacted_watermarks(
                    job=job,
                    state_repo=self._repository_factory.position_states(db),
                    valuation_repo=self._repository_factory.valuations(db),
                )
                terminal_transition_started.set()
                await self._update_reset_watermark_job_terminal_status(
                    job=job,
                    job_repo=self._repository_factory.reprocessing_jobs(db),
                    should_complete_job=should_complete_job,
                )

    async def _process_with_lease_renewal(
        self,
        *,
        job,
        job_type: str,
        operation: Callable[[asyncio.Event], Awaitable[None]],
    ) -> None:
        loop = asyncio.get_running_loop()
        authority_read_started_at = loop.time()
        measured_remaining_lease_seconds = await self._read_lease_remaining_seconds(
            job,
            timeout_seconds=self._lease_renewal_io_timeout_seconds,
        )
        # Keep the measured deadline absolute across task scheduling. The
        # database reports the remaining budget at statement time; anchoring it
        # to the read start prevents a delayed renewal task from extending it.
        initial_lease_deadline = authority_read_started_at + measured_remaining_lease_seconds
        if initial_lease_deadline <= loop.time():
            raise ReprocessingJobOwnershipLostError(
                f"reprocessing job {self._job_id(job)} lease authority was lost"
            )
        stop_renewal = asyncio.Event()
        terminal_transition_started = asyncio.Event()

        async def run_operation() -> None:
            try:
                await operation(terminal_transition_started)
            finally:
                # Set before this task becomes done, so a renewal unblocked by the
                # terminal commit cannot misclassify that terminal state as lease loss.
                stop_renewal.set()

        operation_task = asyncio.create_task(run_operation())
        renewal_task = asyncio.create_task(
            self._renew_lease_while_processing(
                job=job,
                job_type=job_type,
                stop_event=stop_renewal,
                terminal_transition_started=terminal_transition_started,
                initial_lease_deadline=initial_lease_deadline,
            )
        )
        try:
            done, _pending = await asyncio.wait(
                {operation_task, renewal_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if renewal_task in done:
                await renewal_task
            await operation_task
        finally:
            stop_renewal.set()
            if not operation_task.done():
                operation_task.cancel()
            await asyncio.gather(operation_task, renewal_task, return_exceptions=True)

    async def _renew_lease_while_processing(
        self,
        *,
        job,
        job_type: str,
        stop_event: asyncio.Event,
        terminal_transition_started: asyncio.Event,
        initial_lease_deadline: float | None = None,
    ) -> None:
        loop = asyncio.get_running_loop()
        scheduled_at = loop.time()
        if initial_lease_deadline is None:
            remaining_lease_seconds = await self._read_lease_remaining_seconds(
                job,
                timeout_seconds=self._lease_renewal_io_timeout_seconds,
            )
            scheduled_at = loop.time()
            lease_deadline = scheduled_at + remaining_lease_seconds
        else:
            lease_deadline = initial_lease_deadline
            remaining_lease_seconds = lease_deadline - loop.time()
            if remaining_lease_seconds <= 0:
                raise ReprocessingJobOwnershipLostError(
                    f"reprocessing job {self._job_id(job)} lease authority was lost"
                )
        # A delayed worker may receive less authority than the normal heartbeat interval.
        # Wake at the measured durable deadline rather than sleeping past it.
        next_renewal_at = min(
            scheduled_at + self._lease_renewal_interval_seconds,
            lease_deadline,
        )
        while True:
            wait_seconds = max(0.0, next_renewal_at - loop.time())
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=wait_seconds,
                )
                return
            except asyncio.TimeoutError:
                pass

            if stop_event.is_set() or terminal_transition_started.is_set():
                return
            remaining_lease_seconds = lease_deadline - loop.time()
            if remaining_lease_seconds <= 0:
                logger.warning(
                    "Cancelling replay work after lease renewal budget was exhausted.",
                    extra=operation_log_extra(
                        event_name="valuation.reprocessing.lease_renewal_deadline_exhausted",
                        operation="valuation.reprocessing.lease_renewal",
                        status="cancelled",
                        reason_code="renewal_deadline_exhausted",
                        job_id=self._job_id(job),
                        job_type=job_type,
                    ),
                )
                raise ReprocessingJobOwnershipLostError(
                    f"reprocessing job {self._job_id(job)} lease renewal deadline was exhausted"
                )

            outcome = ReprocessingJobTransitionOutcome.NOT_FOUND
            try:
                renewal_timeout_seconds = min(
                    self._lease_renewal_io_timeout_seconds,
                    remaining_lease_seconds,
                )
                async with asyncio.timeout(renewal_timeout_seconds):
                    async for db in self._open_session():
                        async with db.begin():
                            outcome = await self._repository_factory.reprocessing_jobs(
                                db
                            ).renew_lease(
                                self._job_id(job),
                                lease_token=job.lease_token,
                                lease_duration_seconds=self._lease_duration_seconds,
                            )
            except Exception as exc:
                observe_reprocessing_worker_lease_renewal(job_type, "renewal_error")
                logger.warning(
                    "Lease renewal failed; retrying under durable lease fencing.",
                    exc_info=True,
                    extra=operation_log_extra(
                        event_name="valuation.reprocessing.lease_renewal_error",
                        operation="valuation.reprocessing.lease_renewal",
                        status="retrying",
                        reason_code="renewal_error",
                        job_id=self._job_id(job),
                        job_type=job_type,
                        error_type=type(exc).__name__,
                    ),
                )
                if stop_event.is_set() or terminal_transition_started.is_set():
                    return
                next_renewal_at = min(
                    loop.time() + self._lease_renewal_io_timeout_seconds,
                    lease_deadline,
                )
                continue
            if stop_event.is_set() or terminal_transition_started.is_set():
                return
            if outcome is ReprocessingJobTransitionOutcome.APPLIED:
                observe_reprocessing_worker_lease_renewal(job_type, "renewed")
                renewed_read_started_at = loop.time()
                remaining_lease_seconds = await self._read_lease_remaining_seconds(
                    job,
                    timeout_seconds=self._lease_renewal_io_timeout_seconds,
                )
                renewed_at = loop.time()
                lease_deadline = (
                    renewed_at + remaining_lease_seconds - (renewed_at - renewed_read_started_at)
                )
                remaining_lease_seconds = lease_deadline - renewed_at
                if remaining_lease_seconds <= 0:
                    raise ReprocessingJobOwnershipLostError(
                        f"reprocessing job {self._job_id(job)} lease authority was lost"
                    )
                next_renewal_at = min(
                    renewed_at + self._lease_renewal_interval_seconds,
                    lease_deadline,
                )
                continue

            observe_reprocessing_worker_lease_renewal(job_type, "ownership_lost")
            logger.warning(
                "Cancelling replay work after lease renewal lost ownership.",
                extra=operation_log_extra(
                    event_name="valuation.reprocessing.lease_renewal_ownership_lost",
                    operation="valuation.reprocessing.lease_renewal",
                    status="cancelled",
                    reason_code=outcome.value.lower(),
                    job_id=self._job_id(job),
                    job_type=job_type,
                    transition_outcome=outcome.value,
                ),
            )
            raise ReprocessingJobOwnershipLostError(
                f"reprocessing job {self._job_id(job)} lease renewal lost ownership: "
                f"{outcome.value}"
            )

    async def _read_lease_remaining_seconds(
        self,
        job,
        *,
        timeout_seconds: float | None = None,
    ) -> float:
        """Read the durable lease budget before making a monotonic local decision."""

        async def read() -> float | None:
            async for db in self._open_session():
                async with db.begin():
                    return await self._repository_factory.reprocessing_jobs(
                        db
                    ).get_lease_remaining_seconds(
                        self._job_id(job),
                        lease_token=job.lease_token,
                    )
            return None

        try:
            if timeout_seconds is None:
                remaining = await read()
            else:
                async with asyncio.timeout(timeout_seconds):
                    remaining = await read()
        except TimeoutError as exc:
            raise ReprocessingJobOwnershipLostError(
                f"reprocessing job {self._job_id(job)} lease authority read timed out"
            ) from exc
        except Exception as exc:
            raise ReprocessingJobOwnershipLostError(
                f"reprocessing job {self._job_id(job)} lease authority read failed"
            ) from exc
        if remaining is None or remaining <= 0:
            raise ReprocessingJobOwnershipLostError(
                f"reprocessing job {self._job_id(job)} lease authority was lost"
            )
        return remaining

    @staticmethod
    def _job_id(job) -> int:
        return int(job.job_id if hasattr(job, "job_id") else job.id)

    async def _reset_impacted_watermarks(
        self,
        *,
        job,
        state_repo: PositionStateRepository,
        valuation_repo: ValuationRepository,
    ) -> tuple[bool, str]:
        security_id, earliest_date, new_watermark = _reset_watermark_job_scope(job)
        affected_portfolios = await self._affected_portfolios_for_reset(
            valuation_repo=valuation_repo,
            security_id=security_id,
            earliest_date=earliest_date,
        )
        if not affected_portfolios:
            self._record_reset_watermarks_noop(job, security_id, earliest_date)
            return False, security_id

        keys_to_update = [(p_id, security_id) for p_id in affected_portfolios]
        updated_count = await state_repo.update_watermarks_if_older(
            keys=keys_to_update,
            new_watermark_date=new_watermark,
        )
        _record_reset_watermark_fanout(job, security_id, affected_portfolios, updated_count)
        return True, security_id

    async def _affected_portfolios_for_reset(
        self,
        *,
        valuation_repo: ValuationRepository,
        security_id: str,
        earliest_date: date,
    ) -> list[str]:
        affected_portfolios = await valuation_repo.find_portfolios_holding_security_on_date(
            security_id,
            earliest_date,
        )
        later_holding_portfolios = (
            await valuation_repo.find_portfolios_first_holding_security_after_date(
                security_id,
                earliest_date,
            )
        )
        return sorted(
            {
                *affected_portfolios,
                *later_holding_portfolios,
            }
        )

    @staticmethod
    def _record_reset_watermarks_noop(job, security_id: str, earliest_date: date) -> None:
        observe_reprocessing_worker_jobs_noop(
            "RESET_WATERMARKS",
            "no_impacted_portfolios",
        )
        logger.info(
            "No impacted portfolios are visible yet; requeueing durable replay intent.",
            extra=operation_log_extra(
                event_name="valuation.reprocessing.no_impacted_portfolios",
                operation="valuation.reprocessing.reset_watermarks",
                status="retrying",
                reason_code="no_impacted_portfolios",
                job_id=job.id,
                earliest_impacted_date=earliest_date.isoformat(),
            ),
        )

    async def _update_reset_watermark_job_terminal_status(
        self,
        *,
        job,
        job_repo: ReprocessingJobRepository,
        should_complete_job: bool,
    ) -> None:
        terminal_status = "COMPLETE" if should_complete_job else "PENDING"
        outcome = (
            await job_repo.update_job_status(
                job.id,
                "COMPLETE",
                lease_token=job.lease_token,
            )
            if should_complete_job
            else await job_repo.requeue_owned_effective_dated_job(
                job.id,
                lease_token=job.lease_token,
            )
        )
        successful_outcomes = (
            {ReprocessingJobTransitionOutcome.APPLIED}
            if should_complete_job
            else {
                ReprocessingJobTransitionOutcome.REQUEUED,
                ReprocessingJobTransitionOutcome.COALESCED_PENDING,
            }
        )
        if outcome in successful_outcomes:
            if should_complete_job:
                observe_reprocessing_worker_jobs_completed("RESET_WATERMARKS")
            return

        ownership_lost_reason = (
            "reset_watermarks_terminal_ownership_lost"
            if should_complete_job
            else "reset_watermarks_requeue_ownership_lost"
        )
        observe_reprocessing_stale_skips(ownership_lost_reason, 1)
        logger.warning(
            "Skipping replay job %s after losing job ownership.",
            "completion" if should_complete_job else "requeue",
            extra=operation_log_extra(
                event_name="valuation.reprocessing.ownership_lost",
                operation="valuation.reprocessing.reset_watermarks",
                status="skipped",
                reason_code=ownership_lost_reason,
                job_id=job.id,
                terminal_status=terminal_status,
                transition_outcome=outcome.value,
            ),
        )
        raise ReprocessingJobOwnershipLostError(
            f"reprocessing job {job.id} lease expired before {terminal_status}"
        )

    async def _mark_reset_watermark_job_failed(
        self,
        *,
        job,
        exc: Exception,
    ) -> None:
        logger.error(
            "Reprocessing job processing failed.",
            exc_info=True,
            extra=operation_log_extra(
                event_name="valuation.reprocessing.job_failed",
                operation="valuation.reprocessing.reset_watermarks",
                status="failed",
                reason_code="job_processing_error",
                job_id=job.id,
                error_type=type(exc).__name__,
            ),
        )
        outcome = ReprocessingJobTransitionOutcome.NOT_FOUND
        async for db in self._open_session():
            async with db.begin():
                outcome = await self._repository_factory.reprocessing_jobs(db).update_job_status(
                    job.id,
                    "FAILED",
                    lease_token=job.lease_token,
                    failure_reason=reprocessing_failure_reason(exc),
                )
        if outcome is ReprocessingJobTransitionOutcome.APPLIED:
            observe_reprocessing_worker_jobs_failed("RESET_WATERMARKS")
        else:
            observe_reprocessing_stale_skips(
                f"reset_watermarks_failed_{outcome.value.lower()}",
                1,
            )

    async def _process_fx_revaluation_job(self, *, job) -> None:
        correlation_token = None
        try:
            if job.correlation_id:
                correlation_token = correlation_id_var.set(job.correlation_id)
            await self._process_with_lease_renewal(
                job=job,
                job_type=FX_REVALUATION_JOB_TYPE,
                operation=lambda terminal_started: self._execute_fx_revaluation_job(
                    job,
                    terminal_started,
                ),
            )
        except (FxRevaluationJobOwnershipLostError, ReprocessingJobOwnershipLostError):
            pass
        except Exception as exc:
            async for db in self._open_session():
                async with db.begin():
                    await self._fx_job_processor.mark_failed(
                        job=job,
                        jobs=self._repository_factory.reprocessing_jobs(db),
                        exc=exc,
                    )
        finally:
            if correlation_token is not None:
                correlation_id_var.reset(correlation_token)

    async def _execute_fx_revaluation_job(
        self,
        job,
        terminal_transition_started: asyncio.Event,
    ) -> None:
        async for db in self._open_session():
            async with db.begin():
                await self._fx_job_processor.process(
                    job=job,
                    jobs=self._repository_factory.reprocessing_jobs(db),
                    watermarks=self._repository_factory.position_states(db),
                    revaluation=self._repository_factory.fx_revaluations(db),
                    before_terminal_transition=terminal_transition_started.set,
                )

    async def run(self):
        logger.info(
            "Reprocessing worker started.",
            extra=operation_log_extra(
                event_name="valuation.reprocessing_worker.started",
                operation="valuation.reprocessing_worker.run",
                status="running",
                reason_code="poll_loop_started",
                poll_interval_seconds=self._poll_interval,
            ),
        )
        while self._running:
            try:
                await self._process_batch()
            except Exception:
                logger.error(
                    "Reprocessing worker polling loop failed.",
                    exc_info=True,
                    extra=operation_log_extra(
                        event_name="valuation.reprocessing_worker.poll_loop_failed",
                        operation="valuation.reprocessing_worker.run",
                        status="failed",
                        reason_code="poll_loop_error",
                    ),
                )

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

        logger.info(
            "Reprocessing worker stopped.",
            extra=operation_log_extra(
                event_name="valuation.reprocessing_worker.stopped",
                operation="valuation.reprocessing_worker.run",
                status="stopped",
                reason_code="poll_loop_stopped",
            ),
        )
