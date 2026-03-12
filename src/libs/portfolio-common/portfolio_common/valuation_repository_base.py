import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import cast, delete, func, select, text, tuple_, update
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
    InstrumentReprocessingState,
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

    @async_timed(
        repository="ValuationRepository", method="get_instrument_reprocessing_triggers_count"
    )
    async def get_instrument_reprocessing_triggers_count(self) -> int:
        stmt = select(func.count()).select_from(InstrumentReprocessingState)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    @async_timed(repository="ValuationRepository", method="get_instrument_reprocessing_triggers")
    async def get_instrument_reprocessing_triggers(
        self, batch_size: int
    ) -> List[InstrumentReprocessingState]:
        stmt = (
            select(InstrumentReprocessingState)
            .order_by(
                InstrumentReprocessingState.earliest_impacted_date.asc(),
                InstrumentReprocessingState.updated_at.asc(),
                InstrumentReprocessingState.security_id.asc(),
            )
            .limit(batch_size)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="find_portfolios_for_security")
    async def find_portfolios_for_security(self, security_id: str) -> List[str]:
        stmt = (
            select(PositionState.portfolio_id)
            .where(PositionState.security_id == security_id)
            .distinct()
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

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

    @async_timed(repository="ValuationRepository", method="delete_instrument_reprocessing_triggers")
    async def delete_instrument_reprocessing_triggers(self, security_ids: List[str]) -> None:
        if not security_ids:
            return
        stmt = delete(InstrumentReprocessingState).where(
            InstrumentReprocessingState.security_id.in_(security_ids)
        )
        await self.db.execute(stmt)

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
        self, states: List[PositionState]
    ) -> Dict[Tuple[str, str], date]:
        if not states:
            return {}

        keys_tuple = tuple((s.portfolio_id, s.security_id) for s in states)

        s = aliased(PositionState)
        dps = aliased(DailyPositionSnapshot)
        max_business_date_subq = (
            select(func.max(BusinessDate.date))
            .where(BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE)
            .scalar_subquery()
        )

        date_series_subq = (
            select(
                func.generate_series(
                    s.watermark_date + timedelta(days=1),
                    max_business_date_subq,
                    timedelta(days=1),
                )
                .cast(Date)
                .label("expected_date")
            )
            .correlate(s)
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
            .where(
                tuple_(s.portfolio_id, s.security_id).in_(keys_tuple),
                latest_snapshot_subq.isnot(None),
            )
        )

        result = await self.db.execute(stmt)
        return {(row.portfolio_id, row.security_id): row.contiguous_date for row in result}

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
            .where(
                PositionHistory.security_id == security_id, PositionHistory.position_date <= a_date
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

    @async_timed(repository="ValuationRepository", method="get_states_needing_backfill")
    async def get_states_needing_backfill(
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
        stmt = select(func.max(BusinessDate.date))
        stmt = stmt.where(BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @async_timed(repository="ValuationRepository", method="update_job_status")
    async def update_job_status(
        self,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        epoch: int,
        status: str,
        failure_reason: Optional[str] = None,
    ):
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
            )
            .values(**values_to_update)
        )
        await self.db.execute(stmt)

    @async_timed(repository="ValuationRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(self, batch_size: int) -> List[PortfolioValuationJob]:
        query = text("""
            UPDATE portfolio_valuation_jobs
            SET status = 'PROCESSING', updated_at = now(), attempt_count = attempt_count + 1
            WHERE id IN (
                SELECT id
                FROM portfolio_valuation_jobs
                WHERE status = 'PENDING'
                ORDER BY portfolio_id, security_id, valuation_date
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *;
        """)

        result = await self.db.execute(query, {"batch_size": batch_size})
        claimed_jobs = result.mappings().all()
        if claimed_jobs:
            logger.info("Found and claimed %s eligible valuation jobs.", len(claimed_jobs))
            self._observe_jobs_claimed(len(claimed_jobs))
        return [PortfolioValuationJob(**job) for job in claimed_jobs]

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
    async def find_and_reset_stale_jobs(self, timeout_minutes: int = 15) -> int:
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        stmt = (
            update(PortfolioValuationJob)
            .where(
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
