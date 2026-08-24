# src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py
import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable
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
    reprocessing_worker_batch_timer,
    set_control_queue_failed_stored,
    set_control_queue_oldest_pending_age_seconds,
    set_control_queue_pending,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository

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
from .reprocessing_worker_dependencies import ReprocessingWorkerRepositoryFactory

logger = logging.getLogger(__name__)


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
        """Claim briefly, then commit or roll back every job independently."""
        with reprocessing_worker_batch_timer():
            claimed_jobs = await self._claim_reset_watermark_jobs()
            for job in claimed_jobs:
                await self._process_reset_watermark_job(job=job)

            fx_jobs = await self._claim_fx_revaluation_jobs()
            for job in fx_jobs:
                await self._process_fx_revaluation_job(job=job)

            await self._refresh_queue_metrics()

    async def _claim_reset_watermark_jobs(self):
        claimed_jobs = []
        async for db in self._open_session():
            async with db.begin():
                job_repo = self._repository_factory.reprocessing_jobs(db)
                await job_repo.find_and_reset_stale_jobs(max_attempts=self._max_attempts)
                claimed_jobs = await job_repo.find_and_claim_jobs(
                    "RESET_WATERMARKS",
                    self._batch_size,
                    lease_owner=self._lease_owner,
                    lease_duration_seconds=self._lease_duration_seconds,
                )
        if claimed_jobs:
            observe_reprocessing_worker_jobs_claimed("RESET_WATERMARKS", len(claimed_jobs))
        return claimed_jobs

    async def _claim_fx_revaluation_jobs(self):
        claimed_jobs = []
        async for db in self._open_session():
            async with db.begin():
                repository = self._repository_factory.fx_revaluations(db)
                claimed_jobs = await repository.claim_pending_jobs(
                    self._batch_size,
                    lease_owner=self._lease_owner,
                    lease_duration_seconds=self._lease_duration_seconds,
                )
        if claimed_jobs:
            observe_reprocessing_worker_jobs_claimed(FX_REVALUATION_JOB_TYPE, len(claimed_jobs))
        return claimed_jobs

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
            async for db in self._open_session():
                async with db.begin():
                    should_complete_job, _security_id = await self._reset_impacted_watermarks(
                        job=job,
                        state_repo=self._repository_factory.position_states(db),
                        valuation_repo=self._repository_factory.valuations(db),
                    )
                    await self._update_reset_watermark_job_terminal_status(
                        job=job,
                        job_repo=self._repository_factory.reprocessing_jobs(db),
                        should_complete_job=should_complete_job,
                    )
        except ReprocessingJobOwnershipLostError:
            pass
        except Exception as exc:
            await self._mark_reset_watermark_job_failed(job=job, exc=exc)
        finally:
            if correlation_token is not None:
                correlation_id_var.reset(correlation_token)

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
        if await job_repo.update_job_status(
            job.id,
            terminal_status,
            lease_token=job.lease_token,
        ):
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
        updated = False
        async for db in self._open_session():
            async with db.begin():
                updated = await self._repository_factory.reprocessing_jobs(db).update_job_status(
                    job.id,
                    "FAILED",
                    lease_token=job.lease_token,
                    failure_reason=str(exc),
                )
        if updated:
            observe_reprocessing_worker_jobs_failed("RESET_WATERMARKS")
        else:
            observe_reprocessing_stale_skips("reset_watermarks_terminal_ownership_lost", 1)

    async def _process_fx_revaluation_job(self, *, job) -> None:
        try:
            async for db in self._open_session():
                async with db.begin():
                    await self._fx_job_processor.process(
                        job=job,
                        jobs=self._repository_factory.reprocessing_jobs(db),
                        watermarks=self._repository_factory.position_states(db),
                        revaluation=self._repository_factory.fx_revaluations(db),
                    )
        except FxRevaluationJobOwnershipLostError:
            pass
        except Exception as exc:
            async for db in self._open_session():
                async with db.begin():
                    await self._fx_job_processor.mark_failed(
                        job=job,
                        jobs=self._repository_factory.reprocessing_jobs(db),
                        exc=exc,
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
