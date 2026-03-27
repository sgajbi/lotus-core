# services/query-service/app/repositories/portfolio_repository.py
import logging
from typing import List, Optional

from portfolio_common.database_models import Portfolio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PortfolioRepository:
    """
    Handles read-only database queries for portfolio data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_portfolios(
        self,
        portfolio_id: Optional[str] = None,
        portfolio_ids: Optional[list[str]] = None,
        client_id: Optional[str] = None,
        booking_center_code: Optional[str] = None,
    ) -> List[Portfolio]:
        """
        Retrieves a list of portfolios with optional filters.
        """
        stmt = select(Portfolio)

        if portfolio_id:
            stmt = stmt.filter_by(portfolio_id=portfolio_id)

        if portfolio_ids:
            stmt = stmt.where(Portfolio.portfolio_id.in_(portfolio_ids))

        if client_id:
            stmt = stmt.filter_by(client_id=client_id)

        if booking_center_code:
            stmt = stmt.filter_by(booking_center_code=booking_center_code)

        results = await self.db.execute(stmt.order_by(Portfolio.portfolio_id.asc()))
        portfolios = results.scalars().all()
        logger.info(f"Found {len(portfolios)} portfolios with the given filters.")
        return portfolios

    async def get_by_id(self, portfolio_id: str) -> Optional[Portfolio]:
        """Retrieves a single portfolio by its unique portfolio_id."""
        stmt = select(Portfolio).filter_by(portfolio_id=portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

