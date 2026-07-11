"""SQLAlchemy persistence for portfolio aggregation data and job queues."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    PortfolioAggregationJob,
    PositionTimeseries,
)
from portfolio_common.infrastructure.persistence.timeseries_repository import (
    SharedTimeseriesRepository,
)
from portfolio_common.utils import async_timed
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import aliased

logger = logging.getLogger(__name__)


class PortfolioAggregationRepository(SharedTimeseriesRepository):
    """Persist portfolio aggregation outputs and coordinate aggregation jobs."""

    @async_timed(repository="TimeseriesRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(self, batch_size: int) -> list[PortfolioAggregationJob]:
        job = PortfolioAggregationJob
        snapshot = DailyPositionSnapshot
        position_timeseries = PositionTimeseries
        authoritative_scope = _authoritative_snapshot_scope(job, snapshot)
        completeness_ready = _authoritative_snapshot_exists(
            job, snapshot, authoritative_scope
        ) & ~_missing_position_timeseries_exists(
            job,
            snapshot,
            position_timeseries,
            authoritative_scope,
        )
        result_proxy = await self.db.execute(
            select(job.id)
            .where(job.status == "PENDING", completeness_ready)
            .order_by(job.portfolio_id, job.aggregation_date, job.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        eligible_ids = [row[0] for row in result_proxy.fetchall()]
        if not eligible_ids:
            return []

        result = await self.db.execute(
            update(job)
            .where(job.id.in_(eligible_ids))
            .values(
                status="PROCESSING",
                updated_at=func.now(),
                attempt_count=job.attempt_count + 1,
            )
            .returning(job)
        )
        claimed_jobs = sorted(
            cast(list[PortfolioAggregationJob], result.scalars().all()),
            key=lambda claimed: (
                claimed.portfolio_id,
                claimed.aggregation_date,
                claimed.id,
            ),
        )
        if claimed_jobs:
            logger.info("Found and claimed %s eligible aggregation jobs.", len(claimed_jobs))
        return claimed_jobs

    @async_timed(repository="TimeseriesRepository", method="recover_dispatch_failed_jobs")
    async def recover_dispatch_failed_jobs(
        self,
        job_ids: list[int],
        *,
        max_attempts: int,
        failure_reason: str,
    ) -> dict[str, int]:
        if not job_ids:
            return {"pending_count": 0, "failed_count": 0}

        failed_result = await self.db.execute(
            _dispatch_failed_jobs_statement(
                job_ids=job_ids,
                max_attempts=max_attempts,
                failure_reason=failure_reason,
            )
        )
        pending_result = await self.db.execute(
            _dispatch_retryable_jobs_statement(
                job_ids=job_ids,
                max_attempts=max_attempts,
                failure_reason=failure_reason,
            )
        )
        failed_count = int(failed_result.rowcount or 0)
        pending_count = int(pending_result.rowcount or 0)
        if failed_count or pending_count:
            logger.warning(
                "Recovered aggregation scheduler dispatch failure.",
                extra={
                    "job_ids": job_ids,
                    "pending_count": pending_count,
                    "failed_count": failed_count,
                    "max_attempts": max_attempts,
                },
            )
        return {"pending_count": pending_count, "failed_count": failed_count}

    @async_timed(repository="TimeseriesRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(
        self, timeout_minutes: int = 15, max_attempts: int = 3
    ) -> int:
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stale_rows = cast(
            list[Any],
            (await self.db.execute(_stale_jobs_statement(stale_threshold))).all(),
        )
        if not stale_rows:
            return 0

        failed_job_ids = [row.id for row in stale_rows if row.attempt_count >= max_attempts]
        reset_job_ids = [row.id for row in stale_rows if row.attempt_count < max_attempts]
        await self._mark_stale_jobs_failed(failed_job_ids, stale_threshold, max_attempts)
        return await self._reset_stale_jobs(reset_job_ids, stale_threshold)

    async def _mark_stale_jobs_failed(
        self,
        job_ids: list[int],
        stale_threshold: datetime,
        max_attempts: int,
    ) -> None:
        if not job_ids:
            return
        await self.db.execute(_failed_stale_jobs_statement(job_ids, stale_threshold))
        logger.warning(
            "Marked stale aggregation jobs as FAILED after max attempts.",
            extra={"job_ids": job_ids, "max_attempts": max_attempts},
        )

    async def _reset_stale_jobs(
        self,
        job_ids: list[int],
        stale_threshold: datetime,
    ) -> int:
        if not job_ids:
            return 0
        result = await self.db.execute(_reset_stale_jobs_statement(job_ids, stale_threshold))
        reset_count = int(result.rowcount or 0)
        if reset_count:
            logger.warning(
                "Reset %s stale aggregation jobs from 'PROCESSING' to 'PENDING'.",
                reset_count,
            )
        return reset_count

    @async_timed(repository="TimeseriesRepository", method="get_job_queue_stats")
    async def get_job_queue_stats(self) -> dict[str, Any]:
        row = (
            await self.db.execute(
                select(
                    func.count()
                    .filter(PortfolioAggregationJob.status == "PENDING")
                    .label("pending_count"),
                    func.count()
                    .filter(PortfolioAggregationJob.status == "FAILED")
                    .label("failed_count"),
                    func.min(PortfolioAggregationJob.created_at)
                    .filter(PortfolioAggregationJob.status == "PENDING")
                    .label("oldest_pending_created_at"),
                )
            )
        ).one()
        return {
            "pending_count": int(row.pending_count or 0),
            "failed_count": int(row.failed_count or 0),
            "oldest_pending_created_at": row.oldest_pending_created_at,
        }


def _authoritative_snapshot_scope(job_model, snapshot_model):
    newer_snapshot = aliased(DailyPositionSnapshot)
    newer_snapshot_exists = (
        select(1)
        .where(
            newer_snapshot.portfolio_id == job_model.portfolio_id,
            newer_snapshot.security_id == snapshot_model.security_id,
            newer_snapshot.date <= job_model.aggregation_date,
            or_(
                newer_snapshot.date > snapshot_model.date,
                and_(
                    newer_snapshot.date == snapshot_model.date,
                    newer_snapshot.epoch > snapshot_model.epoch,
                ),
            ),
        )
        .correlate(job_model, snapshot_model)
        .exists()
    )
    return (
        snapshot_model.portfolio_id == job_model.portfolio_id,
        snapshot_model.date <= job_model.aggregation_date,
        ~newer_snapshot_exists,
    )


def _authoritative_snapshot_exists(job_model, snapshot_model, authoritative_scope):
    return select(1).where(*authoritative_scope).correlate(job_model).exists()


def _missing_position_timeseries_exists(
    job_model,
    snapshot_model,
    position_timeseries_model,
    authoritative_scope,
):
    matching_timeseries_exists = (
        select(1)
        .where(
            position_timeseries_model.portfolio_id == job_model.portfolio_id,
            position_timeseries_model.security_id == snapshot_model.security_id,
            position_timeseries_model.date == snapshot_model.date,
            position_timeseries_model.epoch == snapshot_model.epoch,
        )
        .correlate(job_model, snapshot_model)
        .exists()
    )
    return (
        select(1)
        .where(*authoritative_scope, ~matching_timeseries_exists)
        .correlate(job_model)
        .exists()
    )


def _stale_jobs_statement(stale_threshold: datetime):
    return select(
        PortfolioAggregationJob.id,
        PortfolioAggregationJob.attempt_count,
    ).where(
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.updated_at < stale_threshold,
    )


def _failed_stale_jobs_statement(job_ids: list[int], stale_threshold: datetime):
    return (
        _stale_jobs_update_statement(job_ids, stale_threshold)
        .values(
            status="FAILED",
            failure_reason="Stale processing timeout exceeded max attempts",
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _reset_stale_jobs_statement(job_ids: list[int], stale_threshold: datetime):
    return _stale_jobs_update_statement(job_ids, stale_threshold).values(
        status="PENDING",
        updated_at=func.now(),
    )


def _stale_jobs_update_statement(job_ids: list[int], stale_threshold: datetime):
    return update(PortfolioAggregationJob).where(
        PortfolioAggregationJob.id.in_(job_ids),
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.updated_at < stale_threshold,
    )


def _dispatch_failed_jobs_statement(*, job_ids: list[int], max_attempts: int, failure_reason: str):
    return (
        _dispatch_recovery_statement(job_ids)
        .where(PortfolioAggregationJob.attempt_count >= max_attempts)
        .values(status="FAILED", failure_reason=failure_reason, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


def _dispatch_retryable_jobs_statement(
    *, job_ids: list[int], max_attempts: int, failure_reason: str
):
    return (
        _dispatch_recovery_statement(job_ids)
        .where(PortfolioAggregationJob.attempt_count < max_attempts)
        .values(status="PENDING", failure_reason=failure_reason, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


def _dispatch_recovery_statement(job_ids: list[int]):
    return update(PortfolioAggregationJob).where(
        PortfolioAggregationJob.id.in_(job_ids),
        PortfolioAggregationJob.status == "PROCESSING",
    )
