# src/services/query_service/app/services/position_service.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.position_dto import (
    PortfolioPositionHistoryResponse,
    PortfolioPositionsResponse,
)
from ..repositories.position_repository import PositionRepository
from .portfolio_validation import ensure_portfolio_exists
from .position_history_reads import position_history_response
from .position_holdings_reads import (
    effective_holdings_read_as_of_date,
)
from .position_holdings_response import portfolio_holdings_response

logger = logging.getLogger(__name__)


class PositionService:
    """
    Handles the business logic for querying position data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PositionRepository(db)

    async def get_position_history(
        self,
        portfolio_id: str,
        security_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> PortfolioPositionHistoryResponse:
        """
        Retrieves and formats the position history for a given security.
        """
        logger.info(
            f"Fetching position history for security '{security_id}' in portfolio '{portfolio_id}'."
        )

        await ensure_portfolio_exists(repository=self.repo, portfolio_id=portfolio_id)

        return await position_history_response(
            repository=self.repo,
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_portfolio_positions(
        self,
        portfolio_id: str,
        as_of_date: Optional[date] = None,
        include_projected: bool = False,
    ) -> PortfolioPositionsResponse:
        """
        Retrieves and formats the latest positions for a given portfolio.
        """
        logger.info(f"Fetching latest positions for portfolio '{portfolio_id}'.")

        await ensure_portfolio_exists(repository=self.repo, portfolio_id=portfolio_id)
        effective_as_of_date = await effective_holdings_read_as_of_date(
            repository=self.repo,
            requested_as_of_date=as_of_date,
            include_projected=include_projected,
        )

        return await portfolio_holdings_response(
            repository=self.repo,
            portfolio_id=portfolio_id,
            effective_as_of_date=effective_as_of_date,
        )
