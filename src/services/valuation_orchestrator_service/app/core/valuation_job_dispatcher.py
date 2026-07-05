import logging
import time
from typing import Any, List

from portfolio_common.database_models import PortfolioValuationJob
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import observe_valuation_scheduler_jobs_dispatched
from portfolio_common.scheduler_dispatch_recovery import (
    DISPATCH_BUDGET_EXHAUSTED_PHASE,
    DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
    DISPATCH_PUBLISH_FAILURE_PHASE,
    SchedulerDispatchError,
    present_job_ids,
)

from .valuation_job_publisher import ValuationJobPublisher

logger = logging.getLogger(__name__)


class ValuationJobDispatcher:
    """Publishes claimed valuation jobs through the configured dispatch port."""

    def __init__(
        self,
        *,
        valuation_job_publisher: ValuationJobPublisher,
        dispatch_budget_seconds: int,
    ) -> None:
        self._valuation_job_publisher = valuation_job_publisher
        self._dispatch_budget_seconds = dispatch_budget_seconds

    @staticmethod
    def _valuation_job_record_key(job: PortfolioValuationJob) -> str:
        return f"{job.portfolio_id}|{job.security_id}|{job.valuation_date.isoformat()}|{job.epoch}"

    @staticmethod
    def _valuation_job_headers(job: PortfolioValuationJob) -> list[tuple[str, bytes]]:
        if not job.correlation_id:
            return []
        return [("correlation_id", job.correlation_id.encode("utf-8"))]

    @staticmethod
    def _valuation_required_event(job: PortfolioValuationJob) -> dict[str, Any]:
        event = PortfolioValuationRequiredEvent(
            portfolio_id=job.portfolio_id,
            security_id=job.security_id,
            valuation_date=job.valuation_date,
            epoch=job.epoch,
            correlation_id=job.correlation_id,
        )
        payload: dict[str, Any] = event.model_dump(mode="json")
        return payload

    @staticmethod
    def _budget_exhausted(*, started_at: float, budget_seconds: int) -> bool:
        return time.monotonic() - started_at >= budget_seconds

    def _publish_valuation_job(self, job: PortfolioValuationJob) -> None:
        self._valuation_job_publisher.publish_job_requested(
            key=job.portfolio_id,
            value=self._valuation_required_event(job),
            headers=self._valuation_job_headers(job),
        )

    def _raise_dispatch_budget_exhausted(
        self,
        *,
        queued_count: int,
        published_jobs: list[PortfolioValuationJob],
        published_record_keys: list[str],
        remaining_jobs: list[PortfolioValuationJob],
        remaining_record_keys: list[str],
    ) -> None:
        if published_record_keys:
            undelivered_count = self._valuation_job_publisher.confirm_delivery(timeout_seconds=10)
            if undelivered_count:
                affected_record_keys = [*published_record_keys, *remaining_record_keys]
                affected_keys = ", ".join(affected_record_keys)
                raise SchedulerDispatchError(
                    message=(
                        "Delivery confirmation timed out while stopping valuation dispatch "
                        f"after budget exhaustion. Affected job keys: {affected_keys}."
                    ),
                    recovery_job_ids=present_job_ids([*published_jobs, *remaining_jobs]),
                    recovery_record_keys=tuple(affected_record_keys),
                    published_record_keys=tuple(published_record_keys),
                    failure_phase=DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
                )
            observe_valuation_scheduler_jobs_dispatched(len(published_jobs))

        remaining_keys = ", ".join(remaining_record_keys)
        raise SchedulerDispatchError(
            message=(
                "Valuation scheduler dispatch budget exhausted after "
                f"{queued_count} job(s) were queued. Remaining job keys: {remaining_keys}."
            ),
            recovery_job_ids=present_job_ids(remaining_jobs),
            recovery_record_keys=tuple(remaining_record_keys),
            published_record_keys=tuple(published_record_keys),
            failure_phase=DISPATCH_BUDGET_EXHAUSTED_PHASE,
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
        if published_jobs:
            observe_valuation_scheduler_jobs_dispatched(len(published_jobs))
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

    async def dispatch_jobs(self, jobs: List[PortfolioValuationJob]) -> None:
        """Publishes a batch of claimed jobs through the dispatch port."""
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
        dispatch_started_at = time.monotonic()
        for idx, job in enumerate(jobs):
            if self._budget_exhausted(
                started_at=dispatch_started_at,
                budget_seconds=self._dispatch_budget_seconds,
            ):
                self._raise_dispatch_budget_exhausted(
                    queued_count=idx,
                    published_jobs=jobs[:idx],
                    published_record_keys=record_keys[:idx],
                    remaining_jobs=jobs[idx:],
                    remaining_record_keys=record_keys[idx:],
                )
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
        observe_valuation_scheduler_jobs_dispatched(len(jobs))
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
