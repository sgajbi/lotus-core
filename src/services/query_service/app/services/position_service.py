# src/services/query_service/app/services/position_service.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.position_dto import (
    PortfolioPositionHistoryResponse,
    PortfolioPositionsResponse,
)
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.position_repository import PositionRepository
from .position_history import portfolio_position_history_response_data
from .position_holdings import (
    apply_held_since_dates,
    assign_position_weights,
    fallback_valuation_security_ids,
    holdings_data_quality_status,
    holdings_response_as_of_date,
    latest_holdings_evidence_timestamp,
    market_price_freshness_security_ids,
    merge_snapshot_and_history_position_rows,
    portfolio_positions_response_data,
    position_held_since_requests,
    position_response_data,
    position_valuation_data,
    should_fetch_fallback_valuation_map,
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

        if not await self.repo.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

        security_id = normalize_security_id(security_id)
        db_results = await self.repo.get_position_history_by_security(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date,
        )

        return portfolio_position_history_response_data(
            portfolio_id=portfolio_id,
            security_id=security_id,
            db_results=db_results,
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

        needs_default_as_of_date = as_of_date is None and not include_projected
        portfolio_exists = await self.repo.portfolio_exists(portfolio_id)
        if not portfolio_exists:
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        default_as_of_date = (
            await self.repo.get_latest_business_date() if needs_default_as_of_date else as_of_date
        )

        effective_as_of_date = default_as_of_date
        if effective_as_of_date is None and needs_default_as_of_date:
            effective_as_of_date = date.today()

        if effective_as_of_date is not None:
            snapshot_results = await self.repo.get_latest_positions_by_portfolio_as_of_date(
                portfolio_id, effective_as_of_date
            )
            history_results = await self.repo.get_latest_position_history_by_portfolio_as_of_date(
                portfolio_id,
                effective_as_of_date,
            )
        else:
            snapshot_results = await self.repo.get_latest_positions_by_portfolio(portfolio_id)
            history_results = await self.repo.get_latest_position_history_by_portfolio(portfolio_id)

        db_results, history_supplements, snapshot_security_ids = (
            merge_snapshot_and_history_position_rows(
                snapshot_results=snapshot_results,
                history_results=history_results,
            )
        )
        fallback_valuation_map: dict[str, dict[str, float | None]] = {}
        if should_fetch_fallback_valuation_map(
            db_results=db_results,
            history_supplements=history_supplements,
            snapshot_security_ids=snapshot_security_ids,
        ):
            fallback_security_ids = fallback_valuation_security_ids(history_supplements)
            fallback_valuation_map = (
                await self.repo.get_latest_snapshot_valuation_map_as_of_date(
                    portfolio_id,
                    effective_as_of_date,
                    security_ids=fallback_security_ids or None,
                )
                if effective_as_of_date is not None
                else await self.repo.get_latest_snapshot_valuation_map(
                    portfolio_id,
                    security_ids=fallback_security_ids or None,
                )
            )

        positions = []
        for position_row, instrument, pos_state in db_results:
            security_id = normalize_security_id(position_row.security_id)
            is_snapshot_row = security_id in snapshot_security_ids
            valuation_dto = position_valuation_data(
                position_row=position_row,
                is_snapshot_row=is_snapshot_row,
                fallback_valuation=fallback_valuation_map.get(security_id),
            )
            position_dto = position_response_data(
                position_row=position_row,
                instrument=instrument,
                pos_state=pos_state,
                is_snapshot_row=is_snapshot_row,
                valuation=valuation_dto,
            )
            positions.append(position_dto)

        assign_position_weights(positions)

        held_since_requests = position_held_since_requests(
            db_results=db_results,
            positions=positions,
        )

        response_as_of_date = holdings_response_as_of_date(
            effective_as_of_date=effective_as_of_date,
            positions=positions,
        )
        market_price_security_ids = market_price_freshness_security_ids(positions)

        if held_since_requests:
            held_since_map = await self.repo.get_held_since_dates(
                portfolio_id=portfolio_id,
                security_epoch_pairs=[
                    (security_id, epoch) for _, security_id, epoch, _ in held_since_requests
                ],
            )
            latest_market_price_dates = await self.repo.get_latest_market_price_dates(
                security_ids=market_price_security_ids,
                as_of_date=response_as_of_date,
            )
            apply_held_since_dates(
                positions=positions,
                held_since_requests=held_since_requests,
                held_since_map=held_since_map,
            )
        else:
            latest_market_price_dates = await self.repo.get_latest_market_price_dates(
                security_ids=market_price_security_ids,
                as_of_date=response_as_of_date,
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
