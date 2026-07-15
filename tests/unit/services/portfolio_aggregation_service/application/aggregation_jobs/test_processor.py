"""Prove bounded and isolated processing of claimed aggregation jobs."""

import asyncio
from datetime import date, datetime, timezone

import pytest

from src.services.portfolio_aggregation_service.app.application.aggregation_jobs import (
    ProcessClaimedAggregationJobs,
)
from src.services.portfolio_aggregation_service.app.application.portfolio_timeseries import (
    PortfolioTimeseriesMaterializationResult,
    PortfolioTimeseriesMaterializationStatus,
)
from src.services.portfolio_aggregation_service.app.domain.aggregation_records import (
    AggregationJobLease,
    ClaimedAggregationJob,
)

pytestmark = pytest.mark.asyncio


def _job(job_id: int) -> ClaimedAggregationJob:
    return ClaimedAggregationJob(
        id=job_id,
        portfolio_id=f"PORT-{job_id}",
        aggregation_date=date(2026, 7, 15),
        correlation_id=f"corr-{job_id}",
        lease=AggregationJobLease(
            owner="aggregation-runtime-1",
            token=f"lease-{job_id}",
            expires_at=datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc),
        ),
    )


class RecordingMaterializer:
    """Record commands and optionally fail one job while measuring concurrency."""

    def __init__(self, *, failing_job_id: int | None = None) -> None:
        self.failing_job_id = failing_job_id
        self.commands = []
        self.active_count = 0
        self.max_active_count = 0

    async def execute(self, command):
        self.commands.append(command)
        self.active_count += 1
        self.max_active_count = max(self.max_active_count, self.active_count)
        await asyncio.sleep(0)
        self.active_count -= 1
        if command.job_id == self.failing_job_id:
            raise RuntimeError("unexpected worker failure")
        return PortfolioTimeseriesMaterializationResult(
            status=PortfolioTimeseriesMaterializationStatus.COMPLETE,
            target_epoch=3,
        )


async def test_processor_bounds_concurrency_and_preserves_lease_commands() -> None:
    materializer = RecordingMaterializer()
    processor = ProcessClaimedAggregationJobs(materializer=materializer, worker_count=2)

    result = await processor.process([_job(job_id) for job_id in range(1, 6)])

    assert result.complete_count == 5
    assert result.processed_count == 5
    assert materializer.max_active_count == 2
    assert [(command.job_id, command.lease_token) for command in materializer.commands] == [
        (1, "lease-1"),
        (2, "lease-2"),
        (3, "lease-3"),
        (4, "lease-4"),
        (5, "lease-5"),
    ]


async def test_processor_isolates_unexpected_failure_without_cancelling_peer_jobs() -> None:
    materializer = RecordingMaterializer(failing_job_id=2)
    processor = ProcessClaimedAggregationJobs(materializer=materializer, worker_count=2)

    result = await processor.process([_job(1), _job(2), _job(3)])

    assert result.complete_count == 2
    assert result.execution_error_count == 1
    assert result.processed_count == 3
    assert [command.job_id for command in materializer.commands] == [1, 2, 3]
