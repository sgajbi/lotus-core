from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol, TypeVar

from ..domain.aggregation_records import (
    AggregationJobBatchResult,
    AggregationJobLease,
    ClaimedAggregationJob,
    ExpiredAggregationJobRecovery,
)

T = TypeVar("T")


class AggregationSchedulerRepository(Protocol):
    async def get_job_queue_stats(self) -> dict[str, Any]: ...

    async def recover_expired_job_leases(
        self,
        *,
        now: datetime,
        max_attempts: int,
    ) -> ExpiredAggregationJobRecovery: ...

    async def claim_eligible_jobs(
        self,
        *,
        batch_size: int,
        lease: AggregationJobLease,
    ) -> list[ClaimedAggregationJob]: ...


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


class AggregationLeaseTokenGenerator(Protocol):
    def new_hex(self) -> str: ...


class AggregationJobBatchProcessor(Protocol):
    async def process(
        self,
        jobs: list[ClaimedAggregationJob],
    ) -> AggregationJobBatchResult: ...
