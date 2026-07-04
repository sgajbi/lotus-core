from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TypeVar

from portfolio_common.db import get_async_db_session
from portfolio_common.monitoring import (
    set_control_queue_failed_stored,
    set_control_queue_oldest_pending_age_seconds,
    set_control_queue_pending,
)

from ..ports.aggregation_scheduler_ports import (
    AggregationSchedulerRepository,
)
from ..repositories.timeseries_repository import TimeseriesRepository

T = TypeVar("T")


class SqlAlchemyAggregationSchedulerRepositoryProvider:
    async def run_in_transaction(
        self,
        operation: Callable[[AggregationSchedulerRepository], Awaitable[T]],
    ) -> T:
        async for db in get_async_db_session():
            async with db.begin():
                return await operation(TimeseriesRepository(db))
        raise RuntimeError("No aggregation scheduler database session was provided.")


class PrometheusAggregationSchedulerMetricsSink:
    def set_pending(self, count: int) -> None:
        set_control_queue_pending("aggregation", count)

    def set_failed(self, count: int) -> None:
        set_control_queue_failed_stored("aggregation", count)

    def set_oldest_pending_age_seconds(self, age_seconds: float) -> None:
        set_control_queue_oldest_pending_age_seconds("aggregation", age_seconds)


class SystemAggregationSchedulerClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)
