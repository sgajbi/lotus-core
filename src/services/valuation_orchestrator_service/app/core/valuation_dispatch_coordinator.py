import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, List

from portfolio_common.database_models import PortfolioValuationJob
from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import (
    observe_valuation_scheduler_budget_exhausted,
    observe_valuation_scheduler_jobs_claimed,
    observe_valuation_scheduler_producer_backpressure,
)
from portfolio_common.scheduler_dispatch_recovery import (
    DISPATCH_BUDGET_EXHAUSTED_PHASE,
    SchedulerDispatchError,
    dispatch_failure_reason,
)

from ..repositories.valuation_repository import ValuationRepository
from .valuation_job_publisher import ValuationJobPublishError

logger = logging.getLogger(__name__)

SessionProvider = Callable[[], AsyncIterator[Any]]
DispatchJobs = Callable[[List[PortfolioValuationJob]], Awaitable[None]]


@dataclass(frozen=True)
class ValuationDispatchRepositoryFactory:
    valuation_repository_factory: Callable[[Any], ValuationRepository]

    def valuation_repository(self, db: Any) -> ValuationRepository:
        return self.valuation_repository_factory(db)


class ValuationDispatchCoordinator:
    """Claims eligible valuation jobs, dispatches them, and recovers dispatch failures."""

    def __init__(
        self,
        *,
        batch_size: int,
        dispatch_rounds_per_poll: int,
        poll_budget_seconds: int,
        max_attempts: int,
        session_provider: SessionProvider,
        repository_factory: ValuationDispatchRepositoryFactory,
    ) -> None:
        self._batch_size = batch_size
        self._dispatch_rounds_per_poll = dispatch_rounds_per_poll
        self._poll_budget_seconds = poll_budget_seconds
        self._max_attempts = max_attempts
        self._session_provider = session_provider
        self._repository_factory = repository_factory

    @staticmethod
    def _budget_exhausted(*, started_at: float, budget_seconds: int) -> bool:
        return time.monotonic() - started_at >= budget_seconds

    async def recover_dispatch_failure(self, failure: SchedulerDispatchError) -> None:
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
        async for db in self._session_provider():
            async with db.begin():
                repo = self._repository_factory.valuation_repository(db)
                await repo.recover_dispatch_failed_jobs(
                    list(failure.recovery_job_ids),
                    max_attempts=self._max_attempts,
                    failure_reason=dispatch_failure_reason(
                        failure_phase=failure.failure_phase,
                        record_keys=failure.recovery_record_keys,
                    ),
                )

    @staticmethod
    def observe_dispatch_stop(failure: SchedulerDispatchError) -> None:
        if failure.failure_phase == DISPATCH_BUDGET_EXHAUSTED_PHASE:
            observe_valuation_scheduler_budget_exhausted("dispatch")
            return
        cause = failure.__cause__
        if (
            isinstance(cause, ValuationJobPublishError)
            and cause.reason_code == "kafka_publish_back_pressure"
        ):
            observe_valuation_scheduler_producer_backpressure()

    async def claim_and_dispatch_ready_jobs(self, *, dispatch_jobs: DispatchJobs) -> None:
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
            async for db in self._session_provider():
                async with db.begin():
                    repo = self._repository_factory.valuation_repository(db)
                    claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
            if not claimed_jobs:
                break
            observe_valuation_scheduler_jobs_claimed(len(claimed_jobs))
            try:
                await dispatch_jobs(claimed_jobs)
            except SchedulerDispatchError as exc:
                self.observe_dispatch_stop(exc)
                await self.recover_dispatch_failure(exc)
                raise
            if len(claimed_jobs) < self._batch_size:
                break
