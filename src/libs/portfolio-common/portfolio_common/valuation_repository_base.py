import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    Integer,
    String,
    and_,
    cast,
    column,
    func,
    select,
    tuple_,
    update,
    values,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.types import Date

from .config import DEFAULT_BUSINESS_CALENDAR_CODE
from .database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    MarketPrice,
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
)
from .utils import async_timed

logger = logging.getLogger(__name__)


class ValuationRepositoryBase:
    """Shared query/claim logic for valuation worker services."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _observe_jobs_claimed(self, claimed_count: int) -> None:
        """Hook for service-local metrics."""

    def _observe_stale_resets(self, reset_count: int) -> None:
        """Hook for service-local metrics."""

    @staticmethod
    def _newer_epoch_exists(current_job, newer_job):
        return (
            select(newer_job.id)
            .where(
                newer_job.portfolio_id == current_job.portfolio_id,
                newer_job.security_id == current_job.security_id,
                newer_job.valuation_date == current_job.valuation_date,
                newer_job.epoch > current_job.epoch,
            )
            .exists()
        )

    @async_timed(
        repository="ValuationRepository", method="find_open_position_keys_for_security_on_date"
    )
    async def find_open_position_keys_for_security_on_date(
        self, security_id: str, a_date: date
    ) -> List[Tuple[str, str, int]]:
        latest_history_subquery = (
            select(
                PositionHistory.portfolio_id.label("portfolio_id"),
                PositionHistory.security_id.label("security_id"),
                PositionHistory.epoch.label("epoch"),
                PositionHistory.quantity.label("quantity"),
                func.row_number()
                .over(
                    partition_by=(PositionHistory.portfolio_id, PositionHistory.epoch),
                    order_by=[PositionHistory.position_date.desc(), PositionHistory.id.desc()],
                )
                .label("rn"),
            )
            .where(
                PositionHistory.security_id == security_id,
                PositionHistory.position_date <= a_date,
            )
            .subquery()
        )

        stmt = (
            select(
                latest_history_subquery.c.portfolio_id,
                latest_history_subquery.c.security_id,
                latest_history_subquery.c.epoch,
            )
            .join(
                PositionState,
                (PositionState.portfolio_id == latest_history_subquery.c.portfolio_id)
                & (PositionState.security_id == latest_history_subquery.c.security_id)
                & (PositionState.epoch == latest_history_subquery.c.epoch),
            )
            .where(
                latest_history_subquery.c.rn == 1,
                latest_history_subquery.c.quantity > 0,
            )
        )

        result = await self.db.execute(stmt)
        return [(row.portfolio_id, row.security_id, row.epoch) for row in result.all()]

    @async_timed(
        repository="ValuationRepository", method="find_portfolios_holding_security_on_date"
    )
    async def find_portfolios_holding_security_on_date(
        self, security_id: str, a_date: date
    ) -> List[str]:
        latest_history_subquery = (
            select(
                PositionHistory.portfolio_id,
                PositionHistory.quantity,
                func.row_number()
                .over(
                    partition_by=PositionHistory.portfolio_id,
                    order_by=[PositionHistory.position_date.desc(), PositionHistory.id.desc()],
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == PositionHistory.portfolio_id,
                    PositionState.security_id == PositionHistory.security_id,
                    PositionState.epoch == PositionHistory.epoch,
                ),
            )
            .where(
                PositionHistory.security_id == security_id,
                PositionHistory.position_date <= a_date,
            )
            .subquery()
        )

        stmt = select(latest_history_subquery.c.portfolio_id).where(
            latest_history_subquery.c.rn == 1, latest_history_subquery.c.quantity > 0
        )

        result = await self.db.execute(stmt)
        portfolio_ids = result.scalars().all()
        logger.info(
            "Found %s portfolios holding '%s' on or before %s.",
            len(portfolio_ids),
            security_id,
            a_date,
        )
        return portfolio_ids

    @async_timed(repository="ValuationRepository", method="get_portfolios_by_ids")
    async def get_portfolios_by_ids(self, portfolio_ids: List[str]) -> List[Portfolio]:
        if not portfolio_ids:
            return []
        stmt = select(Portfolio).where(Portfolio.portfolio_id.in_(portfolio_ids))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="get_lagging_states")
    async def get_lagging_states(
        self, latest_business_date: date, limit: int
    ) -> List[PositionState]:
        stmt = (
            select(PositionState)
            .where(PositionState.watermark_date < latest_business_date)
            .order_by(PositionState.updated_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="get_terminal_reprocessing_states")
    async def get_terminal_reprocessing_states(
        self, latest_business_date: date, limit: int
    ) -> List[PositionState]:
        stmt = (
            select(PositionState)
            .where(
                PositionState.status == "REPROCESSING",
                PositionState.watermark_date >= latest_business_date,
            )
            .order_by(PositionState.updated_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="find_contiguous_snapshot_dates")
    async def find_contiguous_snapshot_dates(
        self,
        states: List[PositionState],
        first_open_dates: Optional[Dict[Tuple[str, str, int], date]] = None,
    ) -> Dict[Tuple[str, str], date]:
        if not states:
            return {}

        keys_tuple = tuple((s.portfolio_id, s.security_id, s.epoch) for s in states)
        first_open_dates = first_open_dates or {}

        first_open_dates_table = (
            values(
                column("portfolio_id", String),
                column("security_id", String),
                column("epoch", Integer),
                column("first_open_date", Date),
                name="first_open_dates",
            )
            .data(
                [
                    (
                        portfolio_id,
                        security_id,
                        epoch,
                        first_open_date,
                    )
                    for (portfolio_id, security_id, epoch), first_open_date in (
                        first_open_dates.items()
                    )
                ]
            )
            .alias("first_open_dates")
        )

        s = aliased(PositionState)
        dps = aliased(DailyPositionSnapshot)
        max_business_date_subq = (
            select(func.max(BusinessDate.date))
            .where(BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE)
            .scalar_subquery()
        )

        expected_start_date = cast(
            func.greatest(
                s.watermark_date + timedelta(days=1),
                func.coalesce(
                    first_open_dates_table.c.first_open_date,
                    s.watermark_date + timedelta(days=1),
                ),
            ),
            Date,
        )

        date_series_subq = (
            select(
                func.generate_series(
                    expected_start_date,
                    max_business_date_subq,
                    timedelta(days=1),
                )
                .cast(Date)
                .label("expected_date")
            )
            .correlate(s, first_open_dates_table)
            .subquery("date_series")
        )

        first_gap_subq = (
            (
                select(func.min(date_series_subq.c.expected_date))
                .select_from(
                    date_series_subq.outerjoin(
                        dps,
                        (dps.portfolio_id == s.portfolio_id)
                        & (dps.security_id == s.security_id)
                        & (dps.epoch == s.epoch)
                        & (dps.date == date_series_subq.c.expected_date),
                    )
                )
                .where(dps.id.is_(None))
            )
            .correlate(s)
            .scalar_subquery()
        )

        latest_snapshot_subq = (
            (
                select(func.max(dps.date)).where(
                    (dps.portfolio_id == s.portfolio_id)
                    & (dps.security_id == s.security_id)
                    & (dps.epoch == s.epoch)
                )
            )
            .correlate(s)
            .scalar_subquery()
        )

        stmt = (
            select(
                s.portfolio_id,
                s.security_id,
                cast(
                    func.coalesce(first_gap_subq - timedelta(days=1), latest_snapshot_subq), Date
                ).label("contiguous_date"),
            )
            .select_from(s)
            .outerjoin(
                first_open_dates_table,
                (first_open_dates_table.c.portfolio_id == s.portfolio_id)
                & (first_open_dates_table.c.security_id == s.security_id)
                & (first_open_dates_table.c.epoch == s.epoch),
            )
            .where(
                tuple_(s.portfolio_id, s.security_id, s.epoch).in_(keys_tuple),
                latest_snapshot_subq.isnot(None),
            )
        )

        result = await self.db.execute(stmt)
        return {(row.portfolio_id, row.security_id): row.contiguous_date for row in result}

    @async_timed(repository="ValuationRepository", method="get_states_needing_backfill")
    async def get_states_needing_backfill(
        self, latest_business_date: date, limit: int
    ) -> List[PositionState]:
        stmt = (
            select(PositionState)
            .join(Instrument, Instrument.security_id == PositionState.security_id)
            .where(PositionState.watermark_date < latest_business_date)
            .order_by(PositionState.updated_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="get_last_position_history_before_date")
    async def get_last_position_history_before_date(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> Optional[PositionHistory]:
        stmt = (
            select(PositionHistory)
            .filter(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.position_date <= a_date,
                PositionHistory.epoch == epoch,
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_latest_business_date")
    async def get_latest_business_date(self) -> Optional[date]:
        business_date_stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        snapshot_date_stmt = select(func.max(DailyPositionSnapshot.date))
        valuation_job_date_stmt = select(func.max(PortfolioValuationJob.valuation_date))

        business_date = (await self.db.execute(business_date_stmt)).scalar_one_or_none()
        snapshot_date = (await self.db.execute(snapshot_date_stmt)).scalar_one_or_none()
        valuation_job_date = (await self.db.execute(valuation_job_date_stmt)).scalar_one_or_none()

        candidates = [
            d for d in (business_date, snapshot_date, valuation_job_date) if d is not None
        ]
        return max(candidates) if candidates else None

    @async_timed(repository="ValuationRepository", method="update_job_status")
    async def update_job_status(
        self,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        epoch: int,
        status: str,
        failure_reason: Optional[str] = None,
    ) -> bool:
        values_to_update = {
            "status": status,
            "updated_at": func.now(),
            "attempt_count": PortfolioValuationJob.attempt_count + 1,
        }
        if failure_reason:
            values_to_update["failure_reason"] = failure_reason

        stmt = (
            update(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.security_id == security_id,
                PortfolioValuationJob.valuation_date == valuation_date,
                PortfolioValuationJob.epoch == epoch,
                PortfolioValuationJob.status == "PROCESSING",
            )
            .values(**values_to_update)
        )
        result = await self.db.execute(stmt)
        return result.rowcount == 1

    @async_timed(repository="ValuationRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(self, batch_size: int) -> List[PortfolioValuationJob]:
        newer_epoch = aliased(PortfolioValuationJob)
        eligible_ids = (
            select(PortfolioValuationJob.id)
            .where(
                PortfolioValuationJob.status == "PENDING",
                ~self._newer_epoch_exists(PortfolioValuationJob, newer_epoch),
            )
            .order_by(
                PortfolioValuationJob.portfolio_id.asc(),
                PortfolioValuationJob.security_id.asc(),
                PortfolioValuationJob.valuation_date.asc(),
                PortfolioValuationJob.epoch.desc(),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        query = (
            update(PortfolioValuationJob)
            .where(PortfolioValuationJob.id.in_(eligible_ids))
            .values(
                status="PROCESSING",
                updated_at=func.now(),
                attempt_count=PortfolioValuationJob.attempt_count + 1,
            )
            .returning(PortfolioValuationJob)
        )

        result = await self.db.execute(query)
        claimed_models = list(result.scalars().all())
        if claimed_models:
            logger.info("Found and claimed %s eligible valuation jobs.", len(claimed_models))
            self._observe_jobs_claimed(len(claimed_models))
        claimed_models.sort(
            key=lambda job: (job.portfolio_id, job.security_id, job.valuation_date, -job.epoch)
        )
        return claimed_models

    @async_timed(repository="ValuationRepository", method="get_job_queue_stats")
    async def get_job_queue_stats(self) -> Dict[str, Any]:
        newer_epoch = aliased(PortfolioValuationJob)
        actionable_pending = (
            PortfolioValuationJob.status == "PENDING"
        ) & ~self._newer_epoch_exists(PortfolioValuationJob, newer_epoch)
        stmt = select(
            func.count().filter(actionable_pending).label("pending_count"),
            func.count().filter(PortfolioValuationJob.status == "FAILED").label("failed_count"),
            func.min(PortfolioValuationJob.created_at)
            .filter(actionable_pending)
            .label("oldest_pending_created_at"),
        )
        row = (await self.db.execute(stmt)).one()
        return {
            "pending_count": int(row.pending_count or 0),
            "failed_count": int(row.failed_count or 0),
            "oldest_pending_created_at": row.oldest_pending_created_at,
        }

    @async_timed(repository="ValuationRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        stmt = select(Portfolio).filter_by(portfolio_id=portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_instrument")
    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        stmt = select(Instrument).filter_by(security_id=security_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_fx_rate")
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

    @async_timed(repository="ValuationRepository", method="get_latest_price_for_position")
    async def get_latest_price_for_position(
        self, security_id: str, position_date: date
    ) -> Optional[MarketPrice]:
        stmt = (
            select(MarketPrice)
            .filter(MarketPrice.security_id == security_id, MarketPrice.price_date <= position_date)
            .order_by(MarketPrice.price_date.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="upsert_daily_snapshot")
    async def upsert_daily_snapshot(self, snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        try:
            insert_values = {
                "portfolio_id": snapshot.portfolio_id,
                "security_id": snapshot.security_id,
                "date": snapshot.date,
                "epoch": snapshot.epoch,
                "quantity": snapshot.quantity,
                "cost_basis": snapshot.cost_basis,
                "cost_basis_local": snapshot.cost_basis_local,
                "market_price": snapshot.market_price,
                "market_value": snapshot.market_value,
                "market_value_local": snapshot.market_value_local,
                "unrealized_gain_loss": snapshot.unrealized_gain_loss,
                "unrealized_gain_loss_local": snapshot.unrealized_gain_loss_local,
                "valuation_status": snapshot.valuation_status,
            }

            stmt = pg_insert(DailyPositionSnapshot).values(**insert_values)

            update_values = {
                "quantity": stmt.excluded.quantity,
                "cost_basis": stmt.excluded.cost_basis,
                "cost_basis_local": stmt.excluded.cost_basis_local,
                "market_price": stmt.excluded.market_price,
                "market_value": stmt.excluded.market_value,
                "market_value_local": stmt.excluded.market_value_local,
                "unrealized_gain_loss": stmt.excluded.unrealized_gain_loss,
                "unrealized_gain_loss_local": stmt.excluded.unrealized_gain_loss_local,
                "valuation_status": stmt.excluded.valuation_status,
                "updated_at": func.now(),
            }

            final_stmt = stmt.on_conflict_do_update(
                index_elements=["portfolio_id", "security_id", "date", "epoch"], set_=update_values
            ).returning(DailyPositionSnapshot)

            result = await self.db.execute(final_stmt)
            persisted_snapshot = result.scalar_one()

            logger.info(
                "Staged upsert for daily snapshot for %s on %s",
                snapshot.security_id,
                snapshot.date,
            )
            return persisted_snapshot
        except Exception as exc:
            logger.error("Failed to stage upsert for daily snapshot: %s", exc, exc_info=True)
            raise

    @async_timed(repository="ValuationRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(
        self, timeout_minutes: int = 15, max_attempts: int = 3
    ) -> int:
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        newer_epoch = aliased(PortfolioValuationJob)
        stale_jobs_stmt = select(
            PortfolioValuationJob.id,
            PortfolioValuationJob.attempt_count,
            self._newer_epoch_exists(PortfolioValuationJob, newer_epoch).label("has_newer_epoch"),
        ).where(
            PortfolioValuationJob.status == "PROCESSING",
            PortfolioValuationJob.updated_at < stale_threshold,
        )
        stale_rows = (await self.db.execute(stale_jobs_stmt)).all()
        if not stale_rows:
            return 0

        superseded_job_ids = [
            row.id for row in stale_rows if getattr(row, "has_newer_epoch", False)
        ]
        remaining_rows = [row for row in stale_rows if row.id not in superseded_job_ids]
        failed_job_ids = [row.id for row in remaining_rows if row.attempt_count >= max_attempts]
        reset_job_ids = [row.id for row in remaining_rows if row.attempt_count < max_attempts]

        if superseded_job_ids:
            superseded_stmt = (
                update(PortfolioValuationJob)
                .where(
                    PortfolioValuationJob.id.in_(superseded_job_ids),
                    PortfolioValuationJob.status == "PROCESSING",
                    PortfolioValuationJob.updated_at < stale_threshold,
                )
                .values(
                    status="SKIPPED_SUPERSEDED",
                    failure_reason="Superseded by newer valuation epoch.",
                    updated_at=func.now(),
                )
                .execution_options(synchronize_session=False)
            )
            await self.db.execute(superseded_stmt)
            logger.warning(
                "Marked stale superseded valuation jobs as SKIPPED_SUPERSEDED.",
                extra={"job_ids": superseded_job_ids},
            )

        if failed_job_ids:
            failure_stmt = (
                update(PortfolioValuationJob)
                .where(
                    PortfolioValuationJob.id.in_(failed_job_ids),
                    PortfolioValuationJob.status == "PROCESSING",
                    PortfolioValuationJob.updated_at < stale_threshold,
                )
                .values(
                    status="FAILED",
                    failure_reason="Stale processing timeout exceeded max attempts",
                    updated_at=func.now(),
                )
                .execution_options(synchronize_session=False)
            )
            await self.db.execute(failure_stmt)
            logger.warning(
                "Marked stale valuation jobs as FAILED after max attempts.",
                extra={"job_ids": failed_job_ids, "max_attempts": max_attempts},
            )

        if not reset_job_ids:
            return 0

        stmt = (
            update(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.id.in_(reset_job_ids),
                PortfolioValuationJob.status == "PROCESSING",
                PortfolioValuationJob.updated_at < stale_threshold,
            )
            .values(
                status="PENDING",
                updated_at=func.now(),
            )
            .returning(PortfolioValuationJob.id)
        )

        result = await self.db.execute(stmt)
        reset_ids = result.fetchall()
        reset_count = len(reset_ids)

        if reset_count > 0:
            logger.warning(
                "Reset %s stale valuation jobs from 'PROCESSING' to 'PENDING'.",
                reset_count,
            )
            self._observe_stale_resets(reset_count)

        return reset_count

    @async_timed(repository="ValuationRepository", method="get_all_open_positions")
    async def get_all_open_positions(self) -> List[dict]:
        ranked_snapshots_subq = select(
            DailyPositionSnapshot.portfolio_id,
            DailyPositionSnapshot.security_id,
            DailyPositionSnapshot.quantity,
            func.row_number()
            .over(
                partition_by=(
                    DailyPositionSnapshot.portfolio_id,
                    DailyPositionSnapshot.security_id,
                ),
                order_by=DailyPositionSnapshot.date.desc(),
            )
            .label("rn"),
        ).subquery()

        stmt = select(
            ranked_snapshots_subq.c.portfolio_id, ranked_snapshots_subq.c.security_id
        ).where(ranked_snapshots_subq.c.rn == 1, ranked_snapshots_subq.c.quantity > 0)

        result = await self.db.execute(stmt)
        open_positions = result.mappings().all()
        logger.info("Found %s open positions across all portfolios.", len(open_positions))
        return open_positions

    @async_timed(repository="ValuationRepository", method="get_next_price_date")
    async def get_next_price_date(self, security_id: str, after_date: date) -> Optional[date]:
        stmt = (
            select(MarketPrice.price_date)
            .filter(
                MarketPrice.security_id == security_id,
                MarketPrice.price_date > after_date,
            )
            .order_by(MarketPrice.price_date.asc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @async_timed(repository="ValuationRepository", method="get_first_open_dates_for_keys")
    async def get_first_open_dates_for_keys(
        self, keys: List[Tuple[str, str, int]]
    ) -> Dict[Tuple[str, str, int], date]:
        if not keys:
            return {}

        stmt = (
            select(
                PositionHistory.portfolio_id,
                PositionHistory.security_id,
                PositionHistory.epoch,
                func.min(PositionHistory.position_date).label("first_open_date"),
            )
            .where(
                tuple_(
                    PositionHistory.portfolio_id, PositionHistory.security_id, PositionHistory.epoch
                ).in_(keys)
            )
            .group_by(
                PositionHistory.portfolio_id, PositionHistory.security_id, PositionHistory.epoch
            )
        )

        result = await self.db.execute(stmt)
        return {
            (row.portfolio_id, row.security_id, row.epoch): row.first_open_date for row in result
        }
