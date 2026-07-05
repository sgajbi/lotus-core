# src/services/query_service/app/services/position_service.py
import logging
from datetime import date
from typing import Optional

from portfolio_common.logging_utils import operation_log_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.collection_window_policy import validate_required_bounded_date_window
from ..dtos.position_dto import (
    PortfolioMaturitySummaryResponse,
    PortfolioPositionHistoryResponse,
    PortfolioPositionsResponse,
)
from ..repositories.position_repository import PositionRepository
from .portfolio_validation import ensure_portfolio_exists
from .position_history_reads import position_history_response
from .position_holdings_reads import effective_holdings_read_as_of_date
from .position_holdings_response import portfolio_holdings_response
from .position_maturity_summary import portfolio_maturity_summary_response

logger = logging.getLogger(__name__)


class PositionService:
    """
    Handles the business logic for querying position data.
    """

    def __init__(self, db: AsyncSession):
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
        validate_required_bounded_date_window(
            source_product="PositionHistorySeries",
            start_date=start_date,
            end_date=end_date,
        )
        logger.info(
            "Position history query requested.",
            extra=operation_log_extra(
                event_name="query.position_service.history_requested",
                operation="query.position_service.get_position_history",
                status="started",
                reason_code="request_received",
                has_start_date_filter=start_date is not None,
                has_end_date_filter=end_date is not None,
            ),
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
        logger.info(
            "Portfolio positions query requested.",
            extra=operation_log_extra(
                event_name="query.position_service.positions_requested",
                operation="query.position_service.get_portfolio_positions",
                status="started",
                reason_code="request_received",
                has_as_of_date_filter=as_of_date is not None,
                include_projected=include_projected,
            ),
        )

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

    async def get_portfolio_maturity_summary(
        self,
        portfolio_id: str,
        as_of_date: Optional[date] = None,
        horizon_days: int = 90,
        include_projected: bool = False,
    ) -> PortfolioMaturitySummaryResponse:
        """
        Retrieves the Core-owned maturity summary for a portfolio holdings window.
        """
        logger.info(
            "Portfolio maturity summary query requested.",
            extra=operation_log_extra(
                event_name="query.position_service.maturity_summary_requested",
                operation="query.position_service.get_portfolio_maturity_summary",
                status="started",
                reason_code="request_received",
                has_as_of_date_filter=as_of_date is not None,
                include_projected=include_projected,
                horizon_days=horizon_days,
            ),
        )

        holdings = await self.get_portfolio_positions(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            include_projected=include_projected,
        )
        return portfolio_maturity_summary_response(
            portfolio_id=portfolio_id,
            holdings=holdings,
            horizon_days=horizon_days,
            include_projected=include_projected,
        )
