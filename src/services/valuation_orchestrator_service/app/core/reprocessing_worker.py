# src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from portfolio_common.db import get_async_db_session
from portfolio_common.logging_utils import correlation_id_var
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

from ..repositories.valuation_repository import ValuationRepository
from ..settings import get_valuation_runtime_settings

logger = logging.getLogger(__name__)


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
            f"Job {job.id}: Fanned out watermark reset to {updated_count} portfolios "
            f"for security {security_id}."
        )
        return

    stale_skipped_count = targeted_count - updated_count
    observe_reprocessing_stale_skips("reset_watermarks_fanout", stale_skipped_count)
    logger.warning(
        "Job %s: Reset fewer watermarks than targeted for security %s.",
        job.id,
        security_id,
        extra={
            "targeted_count": targeted_count,
            "updated_count": updated_count,
            "stale_skipped_count": stale_skipped_count,
            "security_id": security_id,
            "examples": [f"({p_id},{security_id})" for p_id in affected_portfolios[:3]],
        },
    )


class ReprocessingWorker:
    """
    A background worker that polls for and processes durable reprocessing jobs.
    """

    def __init__(self, poll_interval: int = 10, batch_size: int = 10):
        runtime_settings = get_valuation_runtime_settings(
            worker_poll_interval_default=poll_interval,
            worker_batch_size_default=batch_size,
        )
        self._poll_interval = runtime_settings.reprocessing_worker_poll_interval_seconds
        self._batch_size = runtime_settings.reprocessing_worker_batch_size
        self._stale_timeout_minutes = runtime_settings.reprocessing_worker_stale_timeout_minutes
        self._max_attempts = runtime_settings.reprocessing_worker_max_attempts
        self._running = True
        self._stop_event = asyncio.Event()

    def stop(self):
        logger.info("Reprocessing worker shutdown signal received.")
        self._running = False
        self._stop_event.set()

    async def _update_queue_metrics(self, job_repo: ReprocessingJobRepository):
        queue_stats = await job_repo.get_queue_stats("RESET_WATERMARKS")
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
        """Processes one batch of pending RESET_WATERMARKS jobs."""
        with reprocessing_worker_batch_timer():
            async for db in get_async_db_session():
                async with db.begin():
                    job_repo = ReprocessingJobRepository(db)
                    state_repo = PositionStateRepository(db)
                    valuation_repo = ValuationRepository(db)

                    claimed_jobs = await self._claim_reset_watermark_jobs(job_repo)
                    for job in claimed_jobs:
                        await self._process_reset_watermark_job(
                            job=job,
                            job_repo=job_repo,
                            state_repo=state_repo,
                            valuation_repo=valuation_repo,
                        )

    async def _claim_reset_watermark_jobs(self, job_repo: ReprocessingJobRepository):
        await job_repo.find_and_reset_stale_jobs(
            timeout_minutes=self._stale_timeout_minutes,
            max_attempts=self._max_attempts,
        )
        await self._update_queue_metrics(job_repo)

        claimed_jobs = await job_repo.find_and_claim_jobs("RESET_WATERMARKS", self._batch_size)
        await self._update_queue_metrics(job_repo)
        if claimed_jobs:
            observe_reprocessing_worker_jobs_claimed("RESET_WATERMARKS", len(claimed_jobs))
        return claimed_jobs

    async def _process_reset_watermark_job(
        self,
        *,
        job,
        job_repo: ReprocessingJobRepository,
        state_repo: PositionStateRepository,
        valuation_repo: ValuationRepository,
    ) -> None:
        correlation_token = None
        try:
            if job.correlation_id:
                correlation_token = correlation_id_var.set(job.correlation_id)
            should_complete_job, security_id = await self._reset_impacted_watermarks(
                job=job,
                state_repo=state_repo,
                valuation_repo=valuation_repo,
            )
            await self._update_reset_watermark_job_terminal_status(
                job=job,
                job_repo=job_repo,
                security_id=security_id,
                should_complete_job=should_complete_job,
            )
        except Exception as exc:
            await self._mark_reset_watermark_job_failed(job=job, job_repo=job_repo, exc=exc)
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
        if affected_portfolios:
            return affected_portfolios
        return await valuation_repo.find_portfolios_first_holding_security_after_date(
            security_id,
            earliest_date,
        )

    @staticmethod
    def _record_reset_watermarks_noop(job, security_id: str, earliest_date: date) -> None:
        observe_reprocessing_worker_jobs_noop(
            "RESET_WATERMARKS",
            "no_impacted_portfolios",
        )
        logger.info(
            "Job %s: No impacted portfolios are visible yet for security %s on %s; "
            "requeueing durable replay intent.",
            job.id,
            security_id,
            earliest_date.isoformat(),
        )

    async def _update_reset_watermark_job_terminal_status(
        self,
        *,
        job,
        job_repo: ReprocessingJobRepository,
        security_id: str,
        should_complete_job: bool,
    ) -> None:
        terminal_status = "COMPLETE" if should_complete_job else "PENDING"
        if await job_repo.update_job_status(job.id, terminal_status):
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
            extra={"job_id": job.id, "security_id": security_id},
        )

    @staticmethod
    async def _mark_reset_watermark_job_failed(
        *,
        job,
        job_repo: ReprocessingJobRepository,
        exc: Exception,
    ) -> None:
        logger.error(f"Failed to process reprocessing job {job.id}", exc_info=True)
        updated = await job_repo.update_job_status(job.id, "FAILED", failure_reason=str(exc))
        if updated:
            observe_reprocessing_worker_jobs_failed("RESET_WATERMARKS")
        else:
            observe_reprocessing_stale_skips("reset_watermarks_terminal_ownership_lost", 1)

    async def run(self):
        logger.info(f"ReprocessingWorker started. Polling every {self._poll_interval} seconds.")
        while self._running:
            try:
                await self._process_batch()
            except Exception:
                logger.error("Error in reprocessing worker polling loop.", exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

        logger.info("ReprocessingWorker has stopped.")
