"""Infrastructure adapters for durable portfolio aggregation scheduling."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TypeVar

from portfolio_common.db import get_async_db_session
from portfolio_common.monitoring import (
    observe_control_queue_outcome,
    set_control_queue_failed_stored,
    set_control_queue_oldest_pending_age_seconds,
    set_control_queue_pending,
)

from ..domain.aggregation_jobs.models import (
    AggregationJobBatchResult,
    ExpiredAggregationJobRecovery,
)
from ..ports.aggregation_scheduler_ports import (
    AggregationSchedulerRepository,
)
from .portfolio_aggregation_repository import PortfolioAggregationRepository

T = TypeVar("T")


class SqlAlchemyAggregationSchedulerRepositoryProvider:
    async def run_in_transaction(
        self,
        operation: Callable[[AggregationSchedulerRepository], Awaitable[T]],
    ) -> T:
        async for db in get_async_db_session():
            async with db.begin():
                return await operation(PortfolioAggregationRepository(db))
        raise RuntimeError("No aggregation scheduler database session was provided.")


class PrometheusAggregationSchedulerMetricsSink:
    def set_pending(self, count: int) -> None:
        set_control_queue_pending("aggregation", count)

    def set_failed(self, count: int) -> None:
        set_control_queue_failed_stored("aggregation", count)

    def set_oldest_pending_age_seconds(self, age_seconds: float) -> None:
        set_control_queue_oldest_pending_age_seconds("aggregation", age_seconds)

    def observe_recovery(self, recovery: ExpiredAggregationJobRecovery) -> None:
        observe_control_queue_outcome(
            "aggregation",
            "lease_recovery",
            "requeued",
            recovery.requeued_count,
        )
        observe_control_queue_outcome(
            "aggregation",
            "lease_recovery",
            "failed",
            recovery.failed_count,
        )

    def observe_claimed(self, count: int) -> None:
        observe_control_queue_outcome("aggregation", "claim", "claimed", count)

    def observe_processed(self, result: AggregationJobBatchResult) -> None:
        outcomes = {
            "complete": result.complete_count,
            "requeued": result.requeued_count,
            "lost_ownership": result.lost_ownership_count,
            "failed": result.failed_count,
            "execution_error": result.execution_error_count,
        }
        for outcome, count in outcomes.items():
            observe_control_queue_outcome("aggregation", "processing", outcome, count)


class SystemAggregationSchedulerClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)
