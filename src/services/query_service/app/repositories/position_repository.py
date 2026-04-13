# src/services/query_service/app/repositories/position_repository.py
import logging
from datetime import date
from typing import Any, List, Optional

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
)
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PositionRepository:
    """
    Handles read-only database queries for position data, ensuring that
    only data from the latest completed epoch is returned.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_latest_business_date(self) -> Optional[date]:
        """Returns latest default-calendar business date for booked-state reads."""
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_held_since_date(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[date]:
        """
        Finds the 'held since date' for a position in a given epoch.
        This is the start of the current continuous holding period.
        """

        last_zero_date_cte = (
            select(func.max(PositionHistory.position_date).label("last_zero_date"))
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.epoch == epoch,
                PositionHistory.quantity == 0,
            )
            .cte("last_zero_date")
        )

        stmt = (
            select(func.min(PositionHistory.position_date))
            .select_from(PositionHistory)
            .join(last_zero_date_cte, text("1=1"), isouter=True)
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.epoch == epoch,
                PositionHistory.position_date
                > func.coalesce(last_zero_date_cte.c.last_zero_date, date.min),
            )
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_held_since_dates(
        self,
        portfolio_id: str,
        security_epoch_pairs: list[tuple[str, int]],
    ) -> dict[tuple[str, int], date]:
        """
        Bulk variant of get_held_since_date.
        Returns held-since dates for (security_id, epoch) keys in one
        query to avoid N+1 round trips.
        """
        if not security_epoch_pairs:
            return {}

        by_epoch: dict[int, list[str]] = {}
        for security_id, epoch in security_epoch_pairs:
            by_epoch.setdefault(epoch, []).append(security_id)

        key_filters = []
        for epoch, security_ids in by_epoch.items():
            key_filters.append(
                and_(
                    PositionHistory.epoch == epoch,
                    PositionHistory.security_id.in_(security_ids),
                )
            )

        if not key_filters:
            return {}

        last_zero_subq = (
            select(
                PositionHistory.security_id.label("security_id"),
                PositionHistory.epoch.label("epoch"),
                func.max(PositionHistory.position_date).label("last_zero_date"),
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                or_(*key_filters),
                PositionHistory.quantity == 0,
            )
            .group_by(PositionHistory.security_id, PositionHistory.epoch)
            .subquery()
        )

        held_since_stmt = (
            select(
                PositionHistory.security_id.label("security_id"),
                PositionHistory.epoch.label("epoch"),
                func.min(PositionHistory.position_date).label("held_since_date"),
            )
            .select_from(PositionHistory)
            .outerjoin(
                last_zero_subq,
                and_(
                    PositionHistory.security_id == last_zero_subq.c.security_id,
                    PositionHistory.epoch == last_zero_subq.c.epoch,
                ),
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                or_(*key_filters),
                PositionHistory.position_date
                > func.coalesce(last_zero_subq.c.last_zero_date, date.min),
            )
            .group_by(PositionHistory.security_id, PositionHistory.epoch)
        )

        rows = (await self.db.execute(held_since_stmt)).all()
        return {
            (str(row.security_id), int(row.epoch)): row.held_since_date
            for row in rows
            if row.held_since_date is not None
        }

    async def get_position_history_by_security(
        self,
        portfolio_id: str,
        security_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Any]:
        """
        Retrieves the time series of position history for a specific security,
        filtered to include only records from the current epoch for that key.
        """
        stmt = (
            select(PositionHistory, PositionState.status.label("reprocessing_status"))
            .join(
                PositionState,
                (PositionHistory.portfolio_id == PositionState.portfolio_id)
                & (PositionHistory.security_id == PositionState.security_id),
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.epoch == PositionState.epoch,
            )
        )

        if start_date:
            stmt = stmt.filter(PositionHistory.position_date >= start_date)

        if end_date:
            stmt = stmt.filter(PositionHistory.position_date <= end_date)

        results = await self.db.execute(stmt.order_by(PositionHistory.position_date.asc()))
        history = results.all()
        logger.info(
            f"Found {len(history)} position history records for security '{security_id}' "
            f"in portfolio '{portfolio_id}'."
        )
        return history

    async def get_latest_positions_by_portfolio(self, portfolio_id: str) -> List[Any]:
        """
        Retrieves the single latest daily snapshot for each security in a given portfolio,
        ensuring that the snapshot belongs to the current epoch for that security.
        It eagerly loads the related Instrument and PositionState data.
        """
        ranked_snapshot_subq = (
            select(
                DailyPositionSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=DailyPositionSnapshot.security_id,
                    order_by=(
                        DailyPositionSnapshot.date.desc(),
                        DailyPositionSnapshot.id.desc(),
                    ),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                    DailyPositionSnapshot.security_id == PositionState.security_id,
                    DailyPositionSnapshot.epoch == PositionState.epoch,
                ),
            )
            .where(DailyPositionSnapshot.portfolio_id == portfolio_id)
            .subquery()
        )

        stmt = (
            select(DailyPositionSnapshot, Instrument, PositionState)
            .join(
                ranked_snapshot_subq,
                and_(
                    DailyPositionSnapshot.id == ranked_snapshot_subq.c.snapshot_id,
                    ranked_snapshot_subq.c.rn == 1,
                ),
            )
            .join(Instrument, Instrument.security_id == DailyPositionSnapshot.security_id)
            .join(
                PositionState,
                (PositionState.portfolio_id == DailyPositionSnapshot.portfolio_id)
                & (PositionState.security_id == DailyPositionSnapshot.security_id)
                & (PositionState.epoch == DailyPositionSnapshot.epoch),
            )
            .filter(DailyPositionSnapshot.quantity != 0)
        )

        results = await self.db.execute(stmt)
        positions = results.all()
        logger.info(f"Found {len(positions)} latest positions for portfolio '{portfolio_id}'.")
        return positions

    async def get_latest_position_history_by_portfolio(self, portfolio_id: str) -> List[Any]:
        """
        Fallback query for latest positions per security using position_history
        when daily snapshots are not yet materialized.
        """
        ranked_history_subq = (
            select(
                PositionHistory.id.label("position_history_id"),
                func.row_number()
                .over(
                    partition_by=PositionHistory.security_id,
                    order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionHistory.portfolio_id == PositionState.portfolio_id,
                    PositionHistory.security_id == PositionState.security_id,
                    PositionHistory.epoch == PositionState.epoch,
                ),
            )
            .where(PositionHistory.portfolio_id == portfolio_id)
            .subquery()
        )

        stmt = (
            select(PositionHistory, Instrument, PositionState)
            .join(
                ranked_history_subq,
                and_(
                    PositionHistory.id == ranked_history_subq.c.position_history_id,
                    ranked_history_subq.c.rn == 1,
                ),
            )
            .join(Instrument, Instrument.security_id == PositionHistory.security_id)
            .join(
                PositionState,
                (PositionState.portfolio_id == PositionHistory.portfolio_id)
                & (PositionState.security_id == PositionHistory.security_id)
                & (PositionState.epoch == PositionHistory.epoch),
            )
            .filter(PositionHistory.quantity != 0)
        )

        results = await self.db.execute(stmt)
        positions = results.all()
        logger.info(
            f"Found {len(positions)} fallback position-history rows for portfolio '{portfolio_id}'."
        )
        return positions

    async def get_latest_positions_by_portfolio_as_of_date(
        self, portfolio_id: str, as_of_date: date
    ) -> List[Any]:
        """
        Returns the latest available daily snapshot per security on or before as_of_date,
        constrained to current epoch via PositionState.
        """
        ranked_snapshot_subq = (
            select(
                DailyPositionSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=DailyPositionSnapshot.security_id,
                    order_by=(DailyPositionSnapshot.date.desc(), DailyPositionSnapshot.id.desc()),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                    DailyPositionSnapshot.security_id == PositionState.security_id,
                    DailyPositionSnapshot.epoch == PositionState.epoch,
                ),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date <= as_of_date,
            )
            .subquery()
        )

        stmt = (
            select(DailyPositionSnapshot, Instrument, PositionState)
            .join(
                ranked_snapshot_subq,
                and_(
                    DailyPositionSnapshot.id == ranked_snapshot_subq.c.snapshot_id,
                    ranked_snapshot_subq.c.rn == 1,
                ),
            )
            .join(Instrument, Instrument.security_id == DailyPositionSnapshot.security_id)
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == DailyPositionSnapshot.portfolio_id,
                    PositionState.security_id == DailyPositionSnapshot.security_id,
                    PositionState.epoch == DailyPositionSnapshot.epoch,
                ),
            )
            .filter(DailyPositionSnapshot.quantity != 0)
        )

        results = await self.db.execute(stmt)
        positions = results.all()
        logger.info(
            "Found %s as-of snapshot positions for portfolio '%s' at %s.",
            len(positions),
            portfolio_id,
            as_of_date,
        )
        return positions

    async def get_latest_position_history_by_portfolio_as_of_date(
        self, portfolio_id: str, as_of_date: date
    ) -> List[Any]:
        """
        Fallback latest per-security position_history rows on or before as_of_date,
        constrained to current epoch via PositionState.
        """
        ranked_history_subq = (
            select(
                PositionHistory.id.label("position_history_id"),
                func.row_number()
                .over(
                    partition_by=PositionHistory.security_id,
                    order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionHistory.portfolio_id == PositionState.portfolio_id,
                    PositionHistory.security_id == PositionState.security_id,
                    PositionHistory.epoch == PositionState.epoch,
                ),
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.position_date <= as_of_date,
            )
            .subquery()
        )

        stmt = (
            select(PositionHistory, Instrument, PositionState)
            .join(
                ranked_history_subq,
                and_(
                    PositionHistory.id == ranked_history_subq.c.position_history_id,
                    ranked_history_subq.c.rn == 1,
                ),
            )
            .join(Instrument, Instrument.security_id == PositionHistory.security_id)
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == PositionHistory.portfolio_id,
                    PositionState.security_id == PositionHistory.security_id,
                    PositionState.epoch == PositionHistory.epoch,
                ),
            )
            .filter(PositionHistory.quantity != 0)
        )

        results = await self.db.execute(stmt)
        positions = results.all()
        logger.info(
            "Found %s as-of fallback position-history rows for portfolio '%s' at %s.",
            len(positions),
            portfolio_id,
            as_of_date,
        )
        return positions

    async def get_latest_snapshot_valuation_map(
        self, portfolio_id: str
    ) -> dict[str, dict[str, float | None]]:
        """
        Returns latest available valuation fields by security from daily snapshots,
        regardless of epoch. Used to enrich fallback position-history rows.
        """
        ranked_snapshot_subq = (
            select(
                DailyPositionSnapshot.security_id.label("security_id"),
                DailyPositionSnapshot.market_price.label("market_price"),
                DailyPositionSnapshot.market_value.label("market_value"),
                DailyPositionSnapshot.unrealized_gain_loss.label("unrealized_gain_loss"),
                DailyPositionSnapshot.market_value_local.label("market_value_local"),
                DailyPositionSnapshot.unrealized_gain_loss_local.label(
                    "unrealized_gain_loss_local"
                ),
                func.row_number()
                .over(
                    partition_by=DailyPositionSnapshot.security_id,
                    order_by=(DailyPositionSnapshot.date.desc(), DailyPositionSnapshot.id.desc()),
                )
                .label("rn"),
            )
            .where(DailyPositionSnapshot.portfolio_id == portfolio_id)
            .subquery()
        )

        stmt = select(ranked_snapshot_subq).where(ranked_snapshot_subq.c.rn == 1)
        results = await self.db.execute(stmt)
        rows = results.mappings().all()
        valuation_map: dict[str, dict[str, float | None]] = {}
        for row in rows:
            security_id = row.get("security_id")
            if not security_id:
                continue
            valuation_map[str(security_id)] = {
                "market_price": row.get("market_price"),
                "market_value": row.get("market_value"),
                "unrealized_gain_loss": row.get("unrealized_gain_loss"),
                "market_value_local": row.get("market_value_local"),
                "unrealized_gain_loss_local": row.get("unrealized_gain_loss_local"),
            }
        return valuation_map

    async def get_latest_snapshot_valuation_map_as_of_date(
        self, portfolio_id: str, as_of_date: date
    ) -> dict[str, dict[str, float | None]]:
        """
        Returns latest available valuation fields by security from daily snapshots
        on or before the requested date, regardless of epoch. Used to enrich
        history-backed rows when snapshot materialization lags reprocessing.
        """
        ranked_snapshot_subq = (
            select(
                DailyPositionSnapshot.security_id.label("security_id"),
                DailyPositionSnapshot.market_price.label("market_price"),
                DailyPositionSnapshot.market_value.label("market_value"),
                DailyPositionSnapshot.unrealized_gain_loss.label("unrealized_gain_loss"),
                DailyPositionSnapshot.market_value_local.label("market_value_local"),
                DailyPositionSnapshot.unrealized_gain_loss_local.label(
                    "unrealized_gain_loss_local"
                ),
                func.row_number()
                .over(
                    partition_by=DailyPositionSnapshot.security_id,
                    order_by=(DailyPositionSnapshot.date.desc(), DailyPositionSnapshot.id.desc()),
                )
                .label("rn"),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date <= as_of_date,
            )
            .subquery()
        )

        stmt = select(ranked_snapshot_subq).where(ranked_snapshot_subq.c.rn == 1)
        results = await self.db.execute(stmt)
        rows = results.mappings().all()
        valuation_map: dict[str, dict[str, float | None]] = {}
        for row in rows:
            security_id = row.get("security_id")
            if not security_id:
                continue
            valuation_map[str(security_id)] = {
                "market_price": row.get("market_price"),
                "market_value": row.get("market_value"),
                "unrealized_gain_loss": row.get("unrealized_gain_loss"),
                "market_value_local": row.get("market_value_local"),
                "unrealized_gain_loss_local": row.get("unrealized_gain_loss_local"),
            }
        return valuation_map
