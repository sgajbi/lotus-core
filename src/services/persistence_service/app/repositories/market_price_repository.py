# services/persistence_service/app/repositories/market_price_repository.py
import logging
from datetime import date
from typing import List

from portfolio_common.database_models import DailyPositionSnapshot
from portfolio_common.database_models import MarketPrice as DBMarketPrice
from portfolio_common.events import MarketPriceEvent
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MarketPriceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_portfolios_with_open_position_before_date(
        self, security_id: str, price_date: date
    ) -> List[str]:
        """
        Finds all unique portfolio_ids that have a non-zero position in a given
        security based on the latest snapshot on or before the given price date.
        """
        latest_snapshot_subquery = (
            select(
                DailyPositionSnapshot.portfolio_id,
                DailyPositionSnapshot.quantity,
                func.row_number()
                .over(
                    partition_by=DailyPositionSnapshot.portfolio_id,
                    order_by=DailyPositionSnapshot.date.desc(),
                )
                .label("rn"),
            )
            .where(
                DailyPositionSnapshot.security_id == security_id,
                DailyPositionSnapshot.date <= price_date,
            )
            .subquery()
        )

        stmt = select(latest_snapshot_subquery.c.portfolio_id).where(
            latest_snapshot_subquery.c.rn == 1, latest_snapshot_subquery.c.quantity > 0
        )

        result = await self.db.execute(stmt)
        portfolio_ids = result.scalars().all()
        logger.info(
            f"Found {len(portfolio_ids)} portfolios with an open position in "
            f"'{security_id}' on or before {price_date}."
        )
        return portfolio_ids

    async def create_market_price(self, event: MarketPriceEvent) -> DBMarketPrice:
        """
        Idempotently creates or updates a market price using a native PostgreSQL UPSERT.
        """
        try:
            market_price_data = event.model_dump()

            stmt = pg_insert(DBMarketPrice).values(**market_price_data)

            update_dict = {
                c.name: c
                for c in stmt.excluded
                if c.name not in ["id", "security_id", "price_date"]
            }

            final_stmt = stmt.on_conflict_do_update(
                index_elements=["security_id", "price_date"], set_=update_dict
            )

            await self.db.execute(final_stmt)
            logger.info(
                "Successfully staged UPSERT for market price for "
                f"'{event.security_id}' on '{event.price_date}'."
            )

            return DBMarketPrice(**market_price_data)
        except Exception as e:
            logger.error(
                "Failed to stage UPSERT for market price for "
                f"'{event.security_id}' on '{event.price_date}': {e}",
                exc_info=True,
            )
            raise
