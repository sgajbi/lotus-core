"""SQLAlchemy persistence for portfolio aggregation data and job queues."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Portfolio,
    PortfolioAggregationJob,
    PositionState,
    PositionTimeseries,
)
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.infrastructure.persistence.timeseries_market_data_reader import (
    TimeseriesMarketDataReader,
)
from portfolio_common.infrastructure.persistence.timeseries_upsert_statements import (
    build_portfolio_timeseries_upsert_statement,
)
from portfolio_common.utils import async_timed
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import aliased

from ..domain.aggregation_jobs.models import (
    AggregationJobCompletionDisposition,
    AggregationJobLease,
    ClaimedAggregationJob,
    ExpiredAggregationJobRecovery,
)
from ..domain.portfolio_timeseries.models import (
    PortfolioAggregationScope,
    PortfolioTimeseriesRecord,
)
from ..domain.position_timeseries.models import PositionTimeseriesRecord

logger = logging.getLogger(__name__)

AGGREGATION_REPROCESS_REQUESTED = "REPROCESS_REQUESTED"


class PortfolioAggregationRepository(TimeseriesMarketDataReader):
    """Persist portfolio aggregation outputs and coordinate aggregation jobs."""

    @async_timed(repository="TimeseriesRepository", method="get_current_epoch_for_portfolio")
    async def get_current_epoch_for_portfolio(self, portfolio_id: str) -> int:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        result = await self.db.execute(
            select(func.max(PositionState.epoch)).where(
                func.trim(PositionState.portfolio_id) == normalized_portfolio_id
            )
        )
        return result.scalar_one_or_none() or 0

    @async_timed(repository="TimeseriesRepository", method="upsert_portfolio_timeseries")
    async def upsert_portfolio_timeseries(self, record: PortfolioTimeseriesRecord) -> None:
        try:
            await self.db.execute(build_portfolio_timeseries_upsert_statement(record))
            logger.debug(
                "Staged portfolio time-series upsert.",
                extra={
                    "portfolio_id": record.portfolio_id,
                    "aggregation_date": record.date.isoformat(),
                },
            )
        except Exception as exc:
            logger.error("Failed to stage portfolio time series upsert: %s", exc, exc_info=True)
            raise

    async def complete_or_requeue_job(
        self,
        *,
        job_id: int,
        lease_token: str,
    ) -> AggregationJobCompletionDisposition:
        """Release one job only when its durable lease token still matches."""

        requeue_result = await self.db.execute(
            _owned_claim_update(job_id=job_id, lease_token=lease_token)
            .where(PortfolioAggregationJob.failure_reason == AGGREGATION_REPROCESS_REQUESTED)
            .values(
                status="PENDING",
                failure_reason=None,
                updated_at=func.now(),
                **_cleared_lease_values(),
            )
        )
        if int(requeue_result.rowcount or 0) == 1:
            return AggregationJobCompletionDisposition.REQUEUED

        complete_result = await self.db.execute(
            _owned_claim_update(job_id=job_id, lease_token=lease_token).values(
                status="COMPLETE",
                failure_reason=None,
                updated_at=func.now(),
                **_cleared_lease_values(),
            )
        )
        if int(complete_result.rowcount or 0) == 1:
            return AggregationJobCompletionDisposition.COMPLETE
        return AggregationJobCompletionDisposition.LOST_OWNERSHIP

    async def mark_job_failed(self, *, job_id: int, lease_token: str) -> bool:
        """Fail one job only when its durable lease token still matches."""

        result = await self.db.execute(
            _owned_claim_update(job_id=job_id, lease_token=lease_token).values(
                status="FAILED",
                updated_at=func.now(),
                **_cleared_lease_values(),
            )
        )
        return int(result.rowcount or 0) == 1

    @async_timed(repository="TimeseriesRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> PortfolioAggregationScope | None:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        result = await self.db.execute(
            select(Portfolio).where(func.trim(Portfolio.portfolio_id) == normalized_portfolio_id)
        )
        row = result.scalars().first()
        return _portfolio_aggregation_scope(row) if row is not None else None

    @async_timed(repository="TimeseriesRepository", method="get_all_position_timeseries_for_date")
    async def get_all_position_timeseries_for_date(
        self,
        portfolio_id: str,
        a_date: date,
        epoch: int,
    ) -> list[PositionTimeseriesRecord]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        security_id = func.trim(PositionTimeseries.security_id)
        ranked_rows = (
            select(
                func.trim(PositionTimeseries.portfolio_id).label("portfolio_id"),
                security_id.label("security_id"),
                PositionTimeseries.date.label("date"),
                PositionTimeseries.epoch.label("epoch"),
                func.row_number()
                .over(
                    partition_by=(security_id,),
                    order_by=(PositionTimeseries.date.desc(), PositionTimeseries.epoch.desc()),
                )
                .label("rn"),
            )
            .where(
                func.trim(PositionTimeseries.portfolio_id) == normalized_portfolio_id,
                PositionTimeseries.date <= a_date,
                PositionTimeseries.epoch <= epoch,
            )
            .subquery()
        )
        result = await self.db.execute(
            select(PositionTimeseries)
            .join(
                ranked_rows,
                and_(
                    func.trim(PositionTimeseries.portfolio_id) == ranked_rows.c.portfolio_id,
                    func.trim(PositionTimeseries.security_id) == ranked_rows.c.security_id,
                    PositionTimeseries.date == ranked_rows.c.date,
                    PositionTimeseries.epoch == ranked_rows.c.epoch,
                ),
            )
            .where(ranked_rows.c.rn == 1)
            .order_by(PositionTimeseries.security_id)
        )
        rows = cast(list[PositionTimeseries], result.scalars().all())
        return [_position_timeseries_record(row) for row in rows]

    async def _find_eligible_job_ids(self, batch_size: int) -> list[int]:
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
        return [int(row[0]) for row in result_proxy.fetchall()]

    async def _claim_eligible_job_rows(
        self,
        eligible_ids: list[int],
        *,
        lease: AggregationJobLease,
    ) -> list[PortfolioAggregationJob]:
        if not eligible_ids:
            return []
        job = PortfolioAggregationJob
        result = await self.db.execute(
            update(job)
            .where(job.id.in_(eligible_ids))
            .values(
                status="PROCESSING",
                updated_at=func.now(),
                attempt_count=job.attempt_count + 1,
                lease_owner=lease.owner,
                lease_token=lease.token,
                lease_expires_at=lease.expires_at,
            )
            .returning(job)
        )
        return sorted(
            cast(list[PortfolioAggregationJob], result.scalars().all()),
            key=lambda claimed: (
                claimed.portfolio_id,
                claimed.aggregation_date,
                claimed.id,
            ),
        )

    @async_timed(repository="TimeseriesRepository", method="claim_eligible_jobs")
    async def claim_eligible_jobs(
        self,
        *,
        batch_size: int,
        lease: AggregationJobLease,
    ) -> list[ClaimedAggregationJob]:
        """Claim one ready batch with durable, fenced lease ownership."""

        eligible_ids = await self._find_eligible_job_ids(batch_size)
        claimed_rows = await self._claim_eligible_job_rows(eligible_ids, lease=lease)
        if claimed_rows:
            logger.info("Found and leased %s eligible aggregation jobs.", len(claimed_rows))
        return [_claimed_aggregation_job(row) for row in claimed_rows]

    @async_timed(repository="TimeseriesRepository", method="recover_expired_job_leases")
    async def recover_expired_job_leases(
        self,
        *,
        now: datetime,
        max_attempts: int,
    ) -> ExpiredAggregationJobRecovery:
        """Requeue or fail expired claims while rechecking expiry on every write."""

        expired_rows = cast(
            list[Any],
            (await self.db.execute(_expired_job_leases_statement(now))).all(),
        )
        failed_job_ids = [row.id for row in expired_rows if row.attempt_count >= max_attempts]
        requeued_job_ids = [row.id for row in expired_rows if row.attempt_count < max_attempts]
        failed_count = await self._fail_expired_job_leases(failed_job_ids, now)
        requeued_count = await self._requeue_expired_job_leases(requeued_job_ids, now)
        return ExpiredAggregationJobRecovery(
            requeued_count=requeued_count,
            failed_count=failed_count,
        )

    async def _fail_expired_job_leases(self, job_ids: list[int], now: datetime) -> int:
        if not job_ids:
            return 0
        result = await self.db.execute(
            _expired_job_leases_update(job_ids, now)
            .values(
                status="FAILED",
                failure_reason="Aggregation job lease expired after max attempts",
                updated_at=func.now(),
                **_cleared_lease_values(),
            )
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)

    async def _requeue_expired_job_leases(self, job_ids: list[int], now: datetime) -> int:
        if not job_ids:
            return 0
        result = await self.db.execute(
            _expired_job_leases_update(job_ids, now).values(
                status="PENDING",
                failure_reason=None,
                updated_at=func.now(),
                **_cleared_lease_values(),
            )
        )
        return int(result.rowcount or 0)

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


def _portfolio_aggregation_scope(row: Portfolio) -> PortfolioAggregationScope:
    return PortfolioAggregationScope(
        portfolio_id=str(row.portfolio_id),
        base_currency=str(row.base_currency),
    )


def _position_timeseries_record(row: PositionTimeseries) -> PositionTimeseriesRecord:
    return PositionTimeseriesRecord(
        portfolio_id=str(row.portfolio_id),
        security_id=str(row.security_id),
        date=cast(date, row.date),
        epoch=int(row.epoch),
        bod_market_value=cast(Decimal, row.bod_market_value),
        bod_cashflow_position=cast(Decimal, row.bod_cashflow_position),
        eod_cashflow_position=cast(Decimal, row.eod_cashflow_position),
        bod_cashflow_portfolio=cast(Decimal, row.bod_cashflow_portfolio),
        eod_cashflow_portfolio=cast(Decimal, row.eod_cashflow_portfolio),
        eod_market_value=cast(Decimal, row.eod_market_value),
        fees=cast(Decimal, row.fees),
        quantity=cast(Decimal, row.quantity),
        cost=cast(Decimal, row.cost),
    )


def _claimed_aggregation_job(row: PortfolioAggregationJob) -> ClaimedAggregationJob:
    lease_expires_at = cast(datetime | None, row.lease_expires_at)
    if row.lease_owner is None or row.lease_token is None or lease_expires_at is None:
        raise ValueError("Claimed aggregation job is missing durable lease identity.")
    return ClaimedAggregationJob(
        id=int(row.id),
        portfolio_id=str(row.portfolio_id),
        aggregation_date=cast(date, row.aggregation_date),
        aggregation_revision=int(row.attempt_count),
        correlation_id=str(row.correlation_id) if row.correlation_id is not None else None,
        lease=AggregationJobLease(
            owner=str(row.lease_owner),
            token=str(row.lease_token),
            expires_at=lease_expires_at,
        ),
    )


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


def _expired_job_leases_statement(now: datetime):
    return select(
        PortfolioAggregationJob.id,
        PortfolioAggregationJob.attempt_count,
    ).where(
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.lease_expires_at <= now,
    )


def _expired_job_leases_update(job_ids: list[int], now: datetime):
    return update(PortfolioAggregationJob).where(
        PortfolioAggregationJob.id.in_(job_ids),
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.lease_expires_at <= now,
    )


def _owned_claim_update(*, job_id: int, lease_token: str):
    return update(PortfolioAggregationJob).where(
        PortfolioAggregationJob.id == job_id,
        PortfolioAggregationJob.status == "PROCESSING",
        PortfolioAggregationJob.lease_token == lease_token,
    )


def _cleared_lease_values() -> dict[str, None]:
    return {
        PortfolioAggregationJob.lease_owner.key: None,
        PortfolioAggregationJob.lease_token.key: None,
        PortfolioAggregationJob.lease_expires_at.key: None,
    }
