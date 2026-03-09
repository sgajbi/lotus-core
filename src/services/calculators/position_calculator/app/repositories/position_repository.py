# services/calculators/position_calculator/app/repositories/position_repository.py
import logging
from datetime import date
from typing import List, Optional

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    PositionHistory,
    Transaction,
)
from portfolio_common.utils import async_timed
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PositionRepository:
    """
    Handles all database interactions for position calculation.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- IMPLEMENTATION FOR NEW METHOD ---
    @async_timed(repository="PositionRepository", method="get_latest_completed_snapshot_date")
    async def get_latest_completed_snapshot_date(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[date]:
        """
        Finds the latest date for which a daily snapshot has been successfully
        created for a given key in a specific epoch.
        """
        stmt = select(func.max(DailyPositionSnapshot.date)).where(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.security_id == security_id,
            DailyPositionSnapshot.epoch == epoch,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @async_timed(repository="PositionRepository", method="get_latest_position_history_date")
    async def get_latest_position_history_date(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[date]:
        """
        Returns the latest position_history date already materialized for the
        key in the target epoch. This is the position calculator's own strongest
        signal that later-dated state already exists, independent of snapshot
        backfill progress.
        """
        stmt = select(func.max(PositionHistory.position_date)).where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.epoch == epoch,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # --- EXISTING METHOD ---
    @async_timed(repository="PositionRepository", method="find_open_security_ids_as_of")
    async def find_open_security_ids_as_of(self, portfolio_id: str, as_of_date: date) -> List[str]:
        """
        Finds all unique security IDs in a portfolio that had a non-zero quantity
        based on the latest available snapshot on or before the specified date.
        """
        # Subquery to rank snapshots for each security within the portfolio by date.
        latest_snapshot_subquery = (
            select(
                DailyPositionSnapshot.security_id,
                DailyPositionSnapshot.quantity,
                func.row_number()
                .over(
                    partition_by=DailyPositionSnapshot.security_id,
                    order_by=DailyPositionSnapshot.date.desc(),
                )
                .label("rn"),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date <= as_of_date,
            )
            .subquery()
        )

        # Select the security_id from the subquery where the rank is 1 (the latest)
        # and the quantity is positive.
        stmt = select(latest_snapshot_subquery.c.security_id).where(
            latest_snapshot_subquery.c.rn == 1,
            latest_snapshot_subquery.c.quantity > 0,
        )

        result = await self.db.execute(stmt)
        security_ids = result.scalars().all()
        logger.info(
            "Found "
            f"{len(security_ids)} open security positions for portfolio "
            f"'{portfolio_id}' as of {as_of_date}."
        )
        return security_ids

    @async_timed(repository="PositionRepository", method="get_all_transactions_for_security")
    async def get_all_transactions_for_security(
        self, portfolio_id: str, security_id: str
    ) -> List[Transaction]:
        """
        Fetches all transactions for a specific security within a portfolio,
        ordered chronologically.
        This is required to replay the entire history accurately.
        """
        stmt = (
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id, Transaction.security_id == security_id)
            .order_by(Transaction.transaction_date.asc(), Transaction.transaction_id.asc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="PositionRepository", method="get_latest_business_date")
    async def get_latest_business_date(self) -> Optional[date]:
        """
        Finds the most recent date present in the dedicated business_dates table.
        """
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        result = await self.db.execute(stmt)
        latest_date = result.scalar_one_or_none()
        return latest_date

    @async_timed(repository="PositionRepository", method="get_last_position_before")
    async def get_last_position_before(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> Optional[PositionHistory]:
        stmt = (
            select(PositionHistory)
            .filter(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.position_date < a_date,
                PositionHistory.epoch == epoch,
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
        )

        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="PositionRepository", method="get_transactions_on_or_after")
    async def get_transactions_on_or_after(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> List[Transaction]:
        stmt = (
            select(Transaction)
            .filter(
                Transaction.portfolio_id == portfolio_id,
                Transaction.security_id == security_id,
                func.date(Transaction.transaction_date) >= a_date,
            )
            .order_by(Transaction.transaction_date.asc(), Transaction.transaction_id.asc())
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="PositionRepository", method="get_transaction_by_id")
    async def get_transaction_by_id(
        self, transaction_id: str, *, portfolio_id: str | None = None
    ) -> Optional[Transaction]:
        stmt = select(Transaction).where(Transaction.transaction_id == transaction_id)
        if portfolio_id:
            stmt = stmt.where(Transaction.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="PositionRepository", method="delete_positions_from")
    async def delete_positions_from(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> int:
        stmt = delete(PositionHistory).where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date >= a_date,
            PositionHistory.epoch == epoch,
        )
        result = await self.db.execute(stmt)
        deleted_count = result.rowcount or 0
        logger.info(
            f"Deleted {deleted_count} stale position records "
            f"for {security_id} in epoch {epoch} from {a_date} onward."
        )
        return deleted_count

    @async_timed(repository="PositionRepository", method="save_positions")
    async def save_positions(self, positions: List[PositionHistory]):
        if not positions:
            logger.debug("No new positions to save.")
            return

        self.db.add_all(positions)
        await self.db.flush()
        logger.info(f"Staged and flushed {len(positions)} new position records for saving.")
