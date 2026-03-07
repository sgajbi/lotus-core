# src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
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
from portfolio_common.monitoring import (
    observe_valuation_worker_jobs_claimed,
    observe_valuation_worker_stale_resets,
)
from portfolio_common.utils import async_timed
from sqlalchemy import cast, delete, func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.types import Date

logger = logging.getLogger(__name__)


class ValuationRepository:
    """
    Handles all database interactions for the position valuation service.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- NEW METHODS ---
    @async_timed(
        repository="ValuationRepository", method="get_instrument_reprocessing_triggers_count"
    )
    async def get_instrument_reprocessing_triggers_count(self) -> int:
        """Counts the number of records in the instrument_reprocessing_state table."""
        stmt = select(func.count()).select_from(InstrumentReprocessingState)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    @async_timed(repository="ValuationRepository", method="get_instrument_reprocessing_triggers")
    async def get_instrument_reprocessing_triggers(
        self, batch_size: int
    ) -> List[InstrumentReprocessingState]:
        """Fetches the oldest pending instrument reprocessing triggers."""
        stmt = (
            select(InstrumentReprocessingState)
            .order_by(InstrumentReprocessingState.updated_at.asc())
            .limit(batch_size)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="find_portfolios_for_security")
    async def find_portfolios_for_security(self, security_id: str) -> List[str]:
        """Finds all unique portfolio_ids that have a PositionState record for a given security."""
        stmt = (
            select(PositionState.portfolio_id)
            .where(PositionState.security_id == security_id)
            .distinct()
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="delete_instrument_reprocessing_triggers")
    async def delete_instrument_reprocessing_triggers(self, security_ids: List[str]) -> None:
        """Deletes instrument reprocessing triggers by their security IDs."""
        if not security_ids:
            return
        stmt = delete(InstrumentReprocessingState).where(
            InstrumentReprocessingState.security_id.in_(security_ids)
        )
        await self.db.execute(stmt)

    # --- END NEW METHODS ---

    @async_timed(repository="ValuationRepository", method="get_portfolios_by_ids")
    async def get_portfolios_by_ids(self, portfolio_ids: List[str]) -> List[Portfolio]:
        """Fetches multiple portfolios by their portfolio_id strings."""
        if not portfolio_ids:
            return []
        stmt = select(Portfolio).where(Portfolio.portfolio_id.in_(portfolio_ids))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="get_lagging_states")
    async def get_lagging_states(
        self, latest_business_date: date, limit: int
    ) -> List[PositionState]:
        """
        Finds keys in the position_state table whose watermark is older than the
        latest business date, indicating a potential need for advancement.
        This includes both CURRENT and REPROCESSING states.
        """
        stmt = (
            select(PositionState)
            .where(PositionState.watermark_date < latest_business_date)
            .order_by(PositionState.updated_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="find_contiguous_snapshot_dates")
    async def find_contiguous_snapshot_dates(
        self, states: List[PositionState]
    ) -> Dict[Tuple[str, str], date]:
        """
        For a list of states, finds the latest date for each key
        that has a continuous sequence of daily snapshots from its watermark.
        """
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

        # Correlated subquery to generate the series of expected dates for each state.
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

        # Subquery to find the first date in the generated series that does NOT
        # have a corresponding snapshot. This is the first "gap".
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

        # Subquery to find the date of the latest existing snapshot for a key.
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

        # Main query to combine the logic.
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
        """
        Finds all unique portfolio_ids that had a non-zero position in a given
        security, based on the latest position_history on or before the given price date.
        """
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
            f"Found {len(portfolio_ids)} portfolios holding '{security_id}' on or before {a_date}."
        )
        return portfolio_ids

    @async_timed(repository="ValuationRepository", method="get_states_needing_backfill")
    async def get_states_needing_backfill(
        self, latest_business_date: date, limit: int
    ) -> List[PositionState]:
        """
        Finds keys in the position_state table whose watermark is older than the
        latest business date, indicating a need for backfilling valuations.
        """
        stmt = (
            select(PositionState)
            .where(PositionState.watermark_date < latest_business_date)
            .order_by(PositionState.updated_at.asc())  # Process oldest changes first
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="get_last_position_history_before_date")
    async def get_last_position_history_before_date(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> Optional[PositionHistory]:
        """
        Fetches the most recent position history record for a specific epoch
        on or before a given date.
        """
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
        """
        Finds the most recent date present in the dedicated business_dates table.
        """
        stmt = select(func.max(BusinessDate.date))
        stmt = stmt.where(BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE)
        result = await self.db.execute(stmt)
        latest_date = result.scalar_one_or_none()
        return latest_date

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
        """Updates the status of a specific valuation job, optionally with a failure reason."""
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
        """
        Finds PENDING valuation jobs, atomically claims them by updating their
        status to PROCESSING, and returns the claimed jobs.
        """
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
            logger.info(f"Found and claimed {len(claimed_jobs)} eligible valuation jobs.")
            observe_valuation_worker_jobs_claimed(len(claimed_jobs))
        return [PortfolioValuationJob(**job) for job in claimed_jobs]

    @async_timed(repository="ValuationRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Fetches a portfolio by its ID."""
        stmt = select(Portfolio).filter_by(portfolio_id=portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_instrument")
    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        """Fetches an instrument by its security ID."""
        stmt = select(Instrument).filter_by(security_id=security_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_fx_rate")
    async def get_fx_rate(
        self, from_currency: str, to_currency: str, a_date: date
    ) -> Optional[FxRate]:
        """Fetches the latest FX rate on or before a given date."""
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
        """
        Finds the most recent market price for a given security on or before the position's date.
        """
        stmt = (
            select(MarketPrice)
            .filter(MarketPrice.security_id == security_id, MarketPrice.price_date <= position_date)
            .order_by(MarketPrice.price_date.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="upsert_daily_snapshot")
    async def upsert_daily_snapshot(self, snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        """
        Idempotently inserts or updates a daily position snapshot and returns the result.
        """
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
                f"Staged upsert for daily snapshot for {snapshot.security_id} on {snapshot.date}"
            )
            return persisted_snapshot
        except Exception as e:
            logger.error(f"Failed to stage upsert for daily snapshot: {e}", exc_info=True)
            raise

    @async_timed(repository="ValuationRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(self, timeout_minutes: int = 15) -> int:
        """
        Finds jobs stuck in 'PROCESSING' state for longer than the timeout
        and resets them to 'PENDING'. This is a recovery mechanism for crashed workers.
        """
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        stmt = (
            update(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.status == "PROCESSING",
                PortfolioValuationJob.updated_at < stale_threshold,
            )
            .values(
                status="PENDING",
                updated_at=func.now(),  # Also update the timestamp to avoid immediate re-claiming
            )
            .returning(PortfolioValuationJob.id)  # Use RETURNING for a reliable count
        )

        result = await self.db.execute(stmt)
        reset_ids = result.fetchall()
        reset_count = len(reset_ids)

        if reset_count > 0:
            logger.warning(
                f"Reset {reset_count} stale valuation jobs from 'PROCESSING' to 'PENDING'."
            )
            observe_valuation_worker_stale_resets(reset_count)

        return reset_count

    @async_timed(repository="ValuationRepository", method="get_all_open_positions")
    async def get_all_open_positions(self) -> List[dict]:
        """
        Finds all unique (portfolio_id, security_id) pairs that currently have
        an open position (quantity > 0) based on their most recent snapshot.
        """
        # Subquery to rank snapshots for each security within each portfolio by date
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

        # Select the portfolio and security IDs from the subquery where the rank is 1
        # (the latest) and the quantity is positive.
        stmt = select(
            ranked_snapshots_subq.c.portfolio_id, ranked_snapshots_subq.c.security_id
        ).where(ranked_snapshots_subq.c.rn == 1, ranked_snapshots_subq.c.quantity > 0)

        result = await self.db.execute(stmt)

        open_positions = result.mappings().all()
        logger.info(f"Found {len(open_positions)} open positions across all portfolios.")
        return open_positions

    @async_timed(repository="ValuationRepository", method="get_next_price_date")
    async def get_next_price_date(self, security_id: str, after_date: date) -> Optional[date]:
        """
        Finds the date of the next available market price for a security strictly after
        a given date.
        """
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
        """
        For a list of (portfolio_id, security_id, epoch) tuples, finds the earliest
        position_date from the position_history table for each.
        """
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
