from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class AggregationSchedulerRepository(Protocol):
    async def get_job_queue_stats(self) -> dict[str, Any]: ...

    async def find_and_reset_stale_jobs(
        self,
        *,
        timeout_minutes: int,
        max_attempts: int,
    ) -> int: ...

    async def find_and_claim_eligible_jobs(self, batch_size: int) -> list[Any]: ...

    async def recover_dispatch_failed_jobs(
        self,
        job_ids: list[int],
        *,
        max_attempts: int,
        failure_reason: str,
    ) -> None: ...


class AggregationSchedulerRepositoryProvider(Protocol):
    async def run_in_transaction(
        self,
        operation: Callable[[AggregationSchedulerRepository], Awaitable[T]],
    ) -> T: ...


class AggregationSchedulerMetricsSink(Protocol):
    def set_pending(self, count: int) -> None: ...

    def set_failed(self, count: int) -> None: ...

    def set_oldest_pending_age_seconds(self, age_seconds: float) -> None: ...


class AggregationSchedulerClock(Protocol):
    def now_utc(self) -> datetime: ...
