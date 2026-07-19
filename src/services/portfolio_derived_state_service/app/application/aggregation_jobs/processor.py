"""Bounded in-process workers for claimed portfolio aggregation jobs."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from ...domain.aggregation_jobs.models import AggregationJobBatchResult, ClaimedAggregationJob
from ..portfolio_timeseries.commands import (
    MaterializePortfolioTimeseriesCommand,
    PortfolioTimeseriesMaterializationResult,
    PortfolioTimeseriesMaterializationStatus,
)

logger = logging.getLogger(__name__)


class PortfolioTimeseriesMaterializer(Protocol):
    """Execute one lease-bearing portfolio materialization command."""

    async def execute(
        self,
        command: MaterializePortfolioTimeseriesCommand,
    ) -> PortfolioTimeseriesMaterializationResult: ...


class ProcessClaimedAggregationJobs:
    """Process a claimed batch with fixed concurrency and failure isolation."""

    def __init__(
        self,
        *,
        materializer: PortfolioTimeseriesMaterializer,
        worker_count: int,
    ) -> None:
        if worker_count < 1:
            raise ValueError("Aggregation job processor requires at least one worker.")
        self._materializer = materializer
        self._worker_count = worker_count

    async def process(
        self,
        jobs: list[ClaimedAggregationJob],
    ) -> AggregationJobBatchResult:
        """Process all claimed jobs without exceeding configured concurrency."""

        if not jobs:
            return AggregationJobBatchResult()
        queue: asyncio.Queue[ClaimedAggregationJob] = asyncio.Queue()
        for job in jobs:
            queue.put_nowait(job)
        statuses: list[PortfolioTimeseriesMaterializationStatus] = []
        execution_error_count = 0

        async def worker() -> None:
            nonlocal execution_error_count
            while not queue.empty():
                try:
                    job = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    result = await self._materializer.execute(
                        MaterializePortfolioTimeseriesCommand(
                            job_id=job.id,
                            lease_token=job.lease.token,
                            portfolio_id=job.portfolio_id,
                            aggregation_date=job.aggregation_date,
                            aggregation_revision=job.aggregation_revision,
                            correlation_id=job.correlation_id,
                        )
                    )
                    statuses.append(result.status)
                except Exception:
                    execution_error_count += 1
                    logger.error(
                        "Unexpected aggregation worker failure; lease expiry will recover the job.",
                        extra={"aggregation_job_id": job.id},
                        exc_info=True,
                    )
                finally:
                    queue.task_done()

        await asyncio.gather(*(worker() for _ in range(min(self._worker_count, len(jobs)))))
        return AggregationJobBatchResult(
            complete_count=statuses.count(PortfolioTimeseriesMaterializationStatus.COMPLETE),
            requeued_count=statuses.count(PortfolioTimeseriesMaterializationStatus.REQUEUED),
            lost_ownership_count=statuses.count(
                PortfolioTimeseriesMaterializationStatus.LOST_OWNERSHIP
            ),
            failed_count=statuses.count(PortfolioTimeseriesMaterializationStatus.FAILED),
            execution_error_count=execution_error_count,
        )
