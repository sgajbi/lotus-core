"""Durable worker processor for effective-dated FX revaluation jobs."""

from __future__ import annotations

import logging

from portfolio_common.logging_utils import correlation_id_var, operation_log_extra
from portfolio_common.monitoring import (
    observe_reprocessing_stale_skips,
    observe_reprocessing_worker_jobs_completed,
    observe_reprocessing_worker_jobs_failed,
    observe_reprocessing_worker_jobs_noop,
)

from ..application.process_fx_revaluation_job import ProcessFxRevaluationJob
from ..domain.fx_revaluation import (
    FX_REVALUATION_JOB_TYPE,
    ClaimedFxRevaluationJob,
    FxReplayExecution,
    RejectedFxRevaluationJob,
)
from ..ports.fx_revaluation import (
    FxRevaluationRepository,
    PositionWatermarkWriter,
    ReprocessingJobStatusWriter,
)

logger = logging.getLogger(__name__)


class FxRevaluationJobProcessor:
    """Apply one claimed FX replay job and record its owned terminal transition."""

    def __init__(self, *, no_impact_attempt_limit: int = 3) -> None:
        if no_impact_attempt_limit <= 0:
            raise ValueError("no_impact_attempt_limit must be positive")
        self._no_impact_attempt_limit = no_impact_attempt_limit

    async def process(
        self,
        *,
        job: ClaimedFxRevaluationJob | RejectedFxRevaluationJob,
        jobs: ReprocessingJobStatusWriter,
        watermarks: PositionWatermarkWriter,
        revaluation: FxRevaluationRepository,
    ) -> None:
        """Process one job without leaking failure or lineage across jobs."""
        correlation_token = None
        try:
            if job.correlation_id:
                correlation_token = correlation_id_var.set(job.correlation_id)
            if isinstance(job, RejectedFxRevaluationJob):
                raise ValueError(job.rejection_reason)
            execution = await ProcessFxRevaluationJob(
                repository=revaluation,
                watermarks=watermarks,
            ).execute(
                pair=job.pair,
                earliest_impacted_date=job.earliest_impacted_date,
            )
            await self._record_execution(job=job, jobs=jobs, execution=execution)
        except Exception as exc:
            await self._mark_failed(job=job, jobs=jobs, exc=exc)
        finally:
            if correlation_token is not None:
                correlation_id_var.reset(correlation_token)

    async def _record_execution(
        self,
        *,
        job: ClaimedFxRevaluationJob,
        jobs: ReprocessingJobStatusWriter,
        execution: FxReplayExecution,
    ) -> None:
        if execution.requeue_required:
            if job.attempt_count >= self._no_impact_attempt_limit:
                observe_reprocessing_worker_jobs_noop(
                    FX_REVALUATION_JOB_TYPE,
                    "no_affected_positions_after_bounded_retry",
                )
                logger.info(
                    "FX correction has no affected positions after bounded visibility retry.",
                    extra=operation_log_extra(
                        event_name="valuation.fx_reprocessing.no_affected_positions",
                        operation="valuation.fx_reprocessing.reset_watermarks",
                        status="complete",
                        reason_code="no_affected_positions_after_bounded_retry",
                        job_id=job.job_id,
                        attempt_count=job.attempt_count,
                        currency_pair=execution.pair.key,
                        earliest_impacted_date=execution.earliest_impacted_date.isoformat(),
                    ),
                )
                await self._transition(job=job, jobs=jobs, status="COMPLETE")
                return
            observe_reprocessing_worker_jobs_noop(
                FX_REVALUATION_JOB_TYPE,
                "no_impacted_position_keys",
            )
            logger.info(
                "No FX-affected position keys are visible; replay intent remains pending.",
                extra=operation_log_extra(
                    event_name="valuation.fx_reprocessing.readiness_deferred",
                    operation="valuation.fx_reprocessing.reset_watermarks",
                    status="retrying",
                    reason_code="no_impacted_position_keys",
                    job_id=job.job_id,
                    attempt_count=job.attempt_count,
                    attempt_limit=self._no_impact_attempt_limit,
                    currency_pair=execution.pair.key,
                    earliest_impacted_date=execution.earliest_impacted_date.isoformat(),
                ),
            )
            await self._transition(job=job, jobs=jobs, status="PENDING")
            return

        if execution.updated_key_count != execution.targeted_key_count:
            observe_reprocessing_stale_skips(
                "fx_revaluation_watermark_already_lagging",
                execution.targeted_key_count - execution.updated_key_count,
            )
        await self._transition(job=job, jobs=jobs, status="COMPLETE")

    @staticmethod
    async def _transition(
        *,
        job: ClaimedFxRevaluationJob,
        jobs: ReprocessingJobStatusWriter,
        status: str,
    ) -> None:
        if await jobs.update_job_status(job.job_id, status):
            if status == "COMPLETE":
                observe_reprocessing_worker_jobs_completed(FX_REVALUATION_JOB_TYPE)
            return
        observe_reprocessing_stale_skips(
            f"fx_revaluation_{status.lower()}_ownership_lost",
            1,
        )
        logger.warning(
            "FX revaluation job transition skipped after ownership loss.",
            extra=operation_log_extra(
                event_name="valuation.fx_reprocessing.ownership_lost",
                operation="valuation.fx_reprocessing.reset_watermarks",
                status="skipped",
                reason_code="job_ownership_lost",
                job_id=job.job_id,
                requested_status=status,
            ),
        )

    @staticmethod
    async def _mark_failed(
        *,
        job: ClaimedFxRevaluationJob | RejectedFxRevaluationJob,
        jobs: ReprocessingJobStatusWriter,
        exc: Exception,
    ) -> None:
        logger.error(
            "FX revaluation job processing failed.",
            exc_info=True,
            extra=operation_log_extra(
                event_name="valuation.fx_reprocessing.job_failed",
                operation="valuation.fx_reprocessing.reset_watermarks",
                status="failed",
                reason_code="job_processing_error",
                job_id=job.job_id,
                error_type=type(exc).__name__,
            ),
        )
        if await jobs.update_job_status(job.job_id, "FAILED", failure_reason=str(exc)):
            observe_reprocessing_worker_jobs_failed(FX_REVALUATION_JOB_TYPE)
        else:
            observe_reprocessing_stale_skips("fx_revaluation_failed_ownership_lost", 1)
