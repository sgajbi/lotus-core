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
from .position_holdings import (
    assign_position_weights,
    holdings_data_quality_status,
    holdings_response_as_of_date,
    latest_holdings_evidence_timestamp,
    merge_snapshot_and_history_position_rows,
    portfolio_position_rows_data,
    portfolio_positions_response_data,
    position_held_since_requests,
)
from .position_holdings_reads import (
    effective_holdings_read_as_of_date,
    fallback_holdings_valuation_map,
    holdings_position_source_rows,
    holdings_support_evidence,
)

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

        snapshot_results, history_results = await holdings_position_source_rows(
            repository=self.repo,
            portfolio_id=portfolio_id,
            effective_as_of_date=effective_as_of_date,
        )

        db_results, history_supplements, snapshot_security_ids = (
            merge_snapshot_and_history_position_rows(
                snapshot_results=snapshot_results,
                history_results=history_results,
            )
        )
        fallback_valuation_map = await fallback_holdings_valuation_map(
            repository=self.repo,
            portfolio_id=portfolio_id,
            effective_as_of_date=effective_as_of_date,
            db_results=db_results,
            history_supplements=history_supplements,
            snapshot_security_ids=snapshot_security_ids,
        )

        positions = portfolio_position_rows_data(
            db_results=db_results,
            snapshot_security_ids=snapshot_security_ids,
            fallback_valuation_map=fallback_valuation_map,
        )
        assign_position_weights(positions)

        held_since_requests = position_held_since_requests(
            db_results=db_results,
            positions=positions,
        )

        response_as_of_date = holdings_response_as_of_date(
            effective_as_of_date=effective_as_of_date,
            positions=positions,
        )
        latest_market_price_dates = await holdings_support_evidence(
            repository=self.repo,
            portfolio_id=portfolio_id,
            positions=positions,
            held_since_requests=held_since_requests,
            response_as_of_date=response_as_of_date,
        )
        return portfolio_positions_response_data(
            portfolio_id=portfolio_id,
            positions=positions,
            response_as_of_date=response_as_of_date,
            data_quality_status=holdings_data_quality_status(
                positions=positions,
                history_supplements=history_supplements,
                response_as_of_date=response_as_of_date,
                latest_market_price_dates=latest_market_price_dates,
            ),
            latest_evidence_timestamp=latest_holdings_evidence_timestamp(db_results),
        )
