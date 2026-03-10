# src/libs/portfolio-common/portfolio_common/position_state_repository.py
import logging
from datetime import date
from typing import Any, Dict, List, Tuple

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import PositionState
from .utils import async_timed

logger = logging.getLogger(__name__)


class PositionStateRepository:
    """
    Handles database operations for the PositionState model, which tracks
    the epoch and watermark for each (portfolio_id, security_id) key.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="PositionStateRepository", method="bulk_update_states")
    async def bulk_update_states(self, updates: List[Dict[str, Any]]) -> int:
        """
        Performs an atomic bulk update of PositionState records.
        `updates` is a list of dicts, each with:
        {
            'portfolio_id': str,
            'security_id': str,
            'expected_epoch': int,
            'watermark_date': date,
            'status': str,
        }
        """
        if not updates:
            return 0

        total_updated = 0
        for update_item in updates:
            stmt = (
                update(PositionState)
                .where(
                    PositionState.portfolio_id == update_item["portfolio_id"],
                    PositionState.security_id == update_item["security_id"],
                    PositionState.epoch == update_item["expected_epoch"],
                )
                .values(
                    watermark_date=update_item["watermark_date"],
                    status=update_item["status"],
                    updated_at=func.now(),
                )
                .execution_options(synchronize_session=False)
            )
            result = await self.db.execute(stmt)
            total_updated += result.rowcount

        return total_updated

    @async_timed(repository="PositionStateRepository", method="get_or_create_state")
    async def get_or_create_state(self, portfolio_id: str, security_id: str) -> PositionState:
        """
        Retrieves the state for a key. If it doesn't exist, it creates it
        with default values (epoch 0, and a far-past watermark date).
        This operation is idempotent.
        """
        stmt = (
            pg_insert(PositionState)
            .values(
                portfolio_id=portfolio_id,
                security_id=security_id,
                epoch=0,
                watermark_date=date(1970, 1, 1),  # A safe default minimum date
                status="CURRENT",
            )
            .on_conflict_do_nothing(index_elements=["portfolio_id", "security_id"])
        )
        await self.db.execute(stmt)

        select_stmt = select(PositionState).filter_by(
            portfolio_id=portfolio_id, security_id=security_id
        )
        result = await self.db.execute(select_stmt)
        return result.scalar_one()

    @async_timed(repository="PositionStateRepository", method="increment_epoch_and_reset_watermark")
    async def increment_epoch_and_reset_watermark(
        self, portfolio_id: str, security_id: str, new_watermark_date: date
    ) -> PositionState:
        """
        Atomically increments the epoch, resets the watermark date, and sets the
        status to 'REPROCESSING' for a given key. Returns the updated state.
        """
        stmt = (
            update(PositionState)
            .where(
                PositionState.portfolio_id == portfolio_id, PositionState.security_id == security_id
            )
            .values(
                epoch=PositionState.epoch + 1,
                watermark_date=new_watermark_date,
                status="REPROCESSING",
                updated_at=func.now(),
            )
            .returning(PositionState)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    @async_timed(repository="PositionStateRepository", method="update_watermarks_if_older")
    async def update_watermarks_if_older(
        self, keys: List[Tuple[str, str]], new_watermark_date: date
    ) -> int:
        """
        For a given list of (portfolio_id, security_id) keys, updates the
        watermark_date only if the new date is older than the existing one.
        Returns the number of rows that were updated.
        """
        if not keys:
            return 0

        stmt = (
            update(PositionState)
            .where(
                tuple_(PositionState.portfolio_id, PositionState.security_id).in_(keys),
                PositionState.watermark_date > new_watermark_date,
            )
            .values(
                watermark_date=new_watermark_date,
                status="REPROCESSING",  # A watermark reset always implies reprocessing is needed
                updated_at=func.now(),
            )
            .returning(PositionState.portfolio_id)
        )
        result = await self.db.execute(stmt)
        updated_rows = result.fetchall()
        return len(updated_rows)
