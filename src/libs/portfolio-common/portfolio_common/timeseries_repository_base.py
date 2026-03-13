import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .database_models import (
    Cashflow,
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PositionState,
    PositionTimeseries,
)
from .utils import async_timed

logger = logging.getLogger(__name__)


class TimeseriesRepositoryBase:
    """Shared repository logic for timeseries worker and portfolio aggregation services."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="TimeseriesRepository", method="get_current_epoch_for_portfolio")
    async def get_current_epoch_for_portfolio(self, portfolio_id: str) -> int:
        stmt = select(func.max(PositionState.epoch)).where(
            PositionState.portfolio_id == portfolio_id
        )
        result = await self.db.execute(stmt)
        max_epoch = result.scalar_one_or_none()
        return max_epoch or 0

    @async_timed(repository="TimeseriesRepository", method="get_all_snapshots_for_date")
    async def get_all_snapshots_for_date(
        self, portfolio_id: str, a_date: date
    ) -> List[DailyPositionSnapshot]:
        stmt = select(DailyPositionSnapshot).filter_by(portfolio_id=portfolio_id, date=a_date)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="upsert_position_timeseries")
    async def upsert_position_timeseries(self, timeseries_record: PositionTimeseries):
        try:
            insert_dict = {
                c.name: getattr(timeseries_record, c.name)
                for c in timeseries_record.__table__.columns
                if c.name not in ["created_at", "updated_at"]
            }
            update_dict = {
                k: v
                for k, v in insert_dict.items()
                if k not in ["portfolio_id", "security_id", "date", "epoch"]
            }
            update_dict["updated_at"] = func.now()

            stmt = pg_insert(PositionTimeseries).values(**insert_dict)
            final_stmt = stmt.on_conflict_do_update(
                index_elements=["portfolio_id", "security_id", "date", "epoch"],
                set_=update_dict,
            )

            await self.db.execute(final_stmt)
            logger.info(
                "Staged upsert for position time series for %s on %s",
                timeseries_record.security_id,
                timeseries_record.date,
            )
        except Exception as exc:
            logger.error("Failed to stage upsert for position time series: %s", exc, exc_info=True)
            raise

    @async_timed(repository="TimeseriesRepository", method="upsert_portfolio_timeseries")
    async def upsert_portfolio_timeseries(self, timeseries_record: PortfolioTimeseries):
        try:
            insert_dict = {
                c.name: getattr(timeseries_record, c.name)
                for c in timeseries_record.__table__.columns
                if c.name not in ["created_at", "updated_at"]
            }
            update_dict = {
                k: v for k, v in insert_dict.items() if k not in ["portfolio_id", "date", "epoch"]
            }
            update_dict["updated_at"] = func.now()

            stmt = pg_insert(PortfolioTimeseries).values(**insert_dict)
            final_stmt = stmt.on_conflict_do_update(
                index_elements=["portfolio_id", "date", "epoch"],
                set_=update_dict,
            )

            await self.db.execute(final_stmt)
            logger.info(
                "Staged upsert for portfolio time series for %s on %s",
                timeseries_record.portfolio_id,
                timeseries_record.date,
            )
        except Exception as exc:
            logger.error("Failed to stage upsert for portfolio time series: %s", exc, exc_info=True)
            raise

    @async_timed(repository="TimeseriesRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(self, batch_size: int) -> List[PortfolioAggregationJob]:
        p1 = PortfolioAggregationJob
        p2 = aliased(PortfolioAggregationJob)
        pts = PortfolioTimeseries
        dps = DailyPositionSnapshot
        position_ts = PositionTimeseries

        prior_day_exists_subq = exists(
            select(1).where(
                pts.portfolio_id == p1.portfolio_id,
                pts.date == p1.aggregation_date - timedelta(days=1),
            )
        ).correlate(p1)

        no_portfolio_history_subq = ~exists(
            select(1).where(pts.portfolio_id == p1.portfolio_id)
        ).correlate(p1)
        first_job_date_subq = (
            select(func.min(p2.aggregation_date))
            .where(p2.portfolio_id == p1.portfolio_id)
            .scalar_subquery()
            .correlate(p1)
        )
        is_first_job_subq = no_portfolio_history_subq & (p1.aggregation_date == first_job_date_subq)

        latest_snapshot_epochs = (
            select(
                dps.security_id.label("security_id"),
                func.max(dps.epoch).label("epoch"),
            )
            .where(
                dps.portfolio_id == p1.portfolio_id,
                dps.date == p1.aggregation_date,
            )
            .group_by(dps.security_id)
            .correlate(p1)
            .subquery()
        )

        expected_snapshot_count_subq = (
            select(func.count()).select_from(latest_snapshot_epochs).scalar_subquery().correlate(p1)
        )

        actual_position_timeseries_count_subq = (
            select(func.count())
            .select_from(latest_snapshot_epochs)
            .join(
                position_ts,
                and_(
                    position_ts.portfolio_id == p1.portfolio_id,
                    position_ts.date == p1.aggregation_date,
                    position_ts.security_id == latest_snapshot_epochs.c.security_id,
                    position_ts.epoch == latest_snapshot_epochs.c.epoch,
                ),
            )
            .scalar_subquery()
            .correlate(p1)
        )

        completeness_ready_subq = (expected_snapshot_count_subq > 0) & (
            actual_position_timeseries_count_subq == expected_snapshot_count_subq
        )

        eligibility_query = (
            select(p1.id)
            .where(
                p1.status == "PENDING",
                (prior_day_exists_subq | is_first_job_subq),
                completeness_ready_subq,
            )
            .order_by(p1.portfolio_id, p1.aggregation_date)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        result_proxy = await self.db.execute(eligibility_query)
        eligible_ids = [row[0] for row in result_proxy.fetchall()]
        if not eligible_ids:
            return []

        update_query = (
            update(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.id.in_(eligible_ids))
            .values(
                status="PROCESSING",
                updated_at=func.now(),
                attempt_count=PortfolioAggregationJob.attempt_count + 1,
            )
            .returning(PortfolioAggregationJob)
        )

        result = await self.db.execute(update_query)
        claimed_jobs = result.scalars().all()
        if claimed_jobs:
            logger.info("Found and claimed %s eligible aggregation jobs.", len(claimed_jobs))
        return claimed_jobs

    @async_timed(repository="TimeseriesRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        result = await self.db.execute(select(Portfolio).filter_by(portfolio_id=portfolio_id))
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_instrument")
    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        result = await self.db.execute(select(Instrument).filter_by(security_id=security_id))
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_instruments_by_ids")
    async def get_instruments_by_ids(self, security_ids: List[str]) -> List[Instrument]:
        if not security_ids:
            return []
        stmt = select(Instrument).where(Instrument.security_id.in_(security_ids))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="get_fx_rate")
    async def get_fx_rate(
        self, from_currency: str, to_currency: str, a_date: date
    ) -> Optional[FxRate]:
        stmt = (
            select(FxRate)
            .filter(
                FxRate.from_currency == from_currency,
                FxRate.to_currency == to_currency,
                FxRate.rate_date <= a_date,
            )
            .order_by(FxRate.rate_date.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_all_position_timeseries_for_date")
    async def get_all_position_timeseries_for_date(
        self, portfolio_id: str, a_date: date, epoch: int
    ) -> List[PositionTimeseries]:
        latest_snapshot_epochs = (
            select(
                DailyPositionSnapshot.security_id.label("security_id"),
                func.max(DailyPositionSnapshot.epoch).label("epoch"),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date == a_date,
            )
            .group_by(DailyPositionSnapshot.security_id)
            .subquery()
        )

        stmt = (
            select(PositionTimeseries)
            .join(
                latest_snapshot_epochs,
                and_(
                    PositionTimeseries.security_id == latest_snapshot_epochs.c.security_id,
                    PositionTimeseries.epoch == latest_snapshot_epochs.c.epoch,
                ),
            )
            .where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.date == a_date,
            )
            .order_by(PositionTimeseries.security_id)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="get_all_cashflows_for_security_date")
    async def get_all_cashflows_for_security_date(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> List[Cashflow]:
        stmt = select(Cashflow).filter_by(
            portfolio_id=portfolio_id, security_id=security_id, cashflow_date=a_date
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="get_last_portfolio_timeseries_before")
    async def get_last_portfolio_timeseries_before(
        self, portfolio_id: str, a_date: date
    ) -> Optional[PortfolioTimeseries]:
        stmt = (
            select(PortfolioTimeseries)
            .filter(
                PortfolioTimeseries.portfolio_id == portfolio_id,
                PortfolioTimeseries.date < a_date,
            )
            .order_by(PortfolioTimeseries.date.desc(), PortfolioTimeseries.epoch.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_latest_snapshots_for_date")
    async def get_latest_snapshots_for_date(
        self, portfolio_id: str, a_date: date
    ) -> List[DailyPositionSnapshot]:
        latest_snapshot_epochs = (
            select(
                DailyPositionSnapshot.security_id.label("security_id"),
                func.max(DailyPositionSnapshot.epoch).label("epoch"),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date == a_date,
            )
            .group_by(DailyPositionSnapshot.security_id)
            .subquery()
        )

        stmt = (
            select(DailyPositionSnapshot)
            .join(
                latest_snapshot_epochs,
                and_(
                    DailyPositionSnapshot.security_id == latest_snapshot_epochs.c.security_id,
                    DailyPositionSnapshot.epoch == latest_snapshot_epochs.c.epoch,
                ),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date == a_date,
            )
            .order_by(DailyPositionSnapshot.security_id)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(
        self, timeout_minutes: int = 15, max_attempts: int = 3
    ) -> int:
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stale_jobs_stmt = select(
            PortfolioAggregationJob.id,
            PortfolioAggregationJob.attempt_count,
        ).where(
            PortfolioAggregationJob.status == "PROCESSING",
            PortfolioAggregationJob.updated_at < stale_threshold,
        )
        stale_rows = (await self.db.execute(stale_jobs_stmt)).all()
        if not stale_rows:
            return 0

        failed_job_ids = [row.id for row in stale_rows if row.attempt_count >= max_attempts]
        reset_job_ids = [row.id for row in stale_rows if row.attempt_count < max_attempts]

        if failed_job_ids:
            failure_stmt = (
                update(PortfolioAggregationJob)
                .where(PortfolioAggregationJob.id.in_(failed_job_ids))
                .values(
                    status="FAILED",
                    failure_reason="Stale processing timeout exceeded max attempts",
                    updated_at=func.now(),
                )
                .execution_options(synchronize_session=False)
            )
            await self.db.execute(failure_stmt)
            logger.warning(
                "Marked stale aggregation jobs as FAILED after max attempts.",
                extra={"job_ids": failed_job_ids, "max_attempts": max_attempts},
            )

        if not reset_job_ids:
            return 0

        stmt = (
            update(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.id.in_(reset_job_ids))
            .values(status="PENDING", updated_at=func.now())
        )

        result = await self.db.execute(stmt)
        reset_count = result.rowcount
        if reset_count > 0:
            logger.warning(
                "Reset %s stale aggregation jobs from 'PROCESSING' to 'PENDING'.",
                reset_count,
            )
        return reset_count

    @async_timed(repository="TimeseriesRepository", method="get_last_snapshot_before")
    async def get_last_snapshot_before(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> Optional[DailyPositionSnapshot]:
        stmt = (
            select(DailyPositionSnapshot)
            .filter(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.security_id == security_id,
                DailyPositionSnapshot.date < a_date,
                DailyPositionSnapshot.epoch == epoch,
            )
            .order_by(DailyPositionSnapshot.date.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()
