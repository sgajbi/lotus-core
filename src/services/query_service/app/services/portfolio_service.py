# services/query-service/app/services/portfolio_service.py
import logging
from typing import Optional

from portfolio_common.logging_utils import operation_log_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.lookup_dto import LookupItem
from ..dtos.portfolio_dto import PortfolioQueryResponse, PortfolioRecord
from ..repositories.portfolio_repository import PortfolioRepository

logger = logging.getLogger(__name__)


class PortfolioService:
    """
    Handles the business logic for querying portfolio data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PortfolioRepository(db)

    async def get_portfolios(
        self,
        portfolio_id: Optional[str] = None,
        portfolio_ids: Optional[list[str]] = None,
        client_id: Optional[str] = None,
        booking_center_code: Optional[str] = None,
    ) -> PortfolioQueryResponse:
        """
        Retrieves a filtered list of portfolios.
        """
        logger.info(
            "Portfolio query requested.",
            extra=operation_log_extra(
                event_name="query.portfolio_service.query_requested",
                operation="query.portfolio_service.get_portfolios",
                status="started",
                reason_code="request_received",
                has_portfolio_id_filter=portfolio_id is not None,
                has_portfolio_ids_filter=bool(portfolio_ids),
                has_client_filter=client_id is not None,
                has_booking_center_filter=booking_center_code is not None,
            ),
        )

        db_results = await self.repo.get_portfolios(
            portfolio_id=portfolio_id,
            portfolio_ids=portfolio_ids,
            client_id=client_id,
            booking_center_code=booking_center_code,
        )

        portfolios = [PortfolioRecord.model_validate(p) for p in db_results]

        return PortfolioQueryResponse(portfolios=portfolios)

    async def search_portfolio_lookup_items(
        self,
        *,
        client_id: str | None = None,
        booking_center_code: str | None = None,
        q: str | None = None,
        limit: int,
    ) -> list[LookupItem]:
        portfolio_ids = await self.repo.search_portfolio_lookup_ids(
            client_id=client_id,
            booking_center_code=booking_center_code,
            q=q,
            limit=limit,
        )
        return [LookupItem(id=portfolio_id, label=portfolio_id) for portfolio_id in portfolio_ids]

    async def list_currency_lookup_items(
        self,
        *,
        q: str | None = None,
        limit: int,
    ) -> list[LookupItem]:
        codes = await self.repo.list_currency_lookup_codes(q=q, limit=limit)
        return [LookupItem(id=code, label=code) for code in codes]

    async def get_portfolio_by_id(self, portfolio_id: str) -> PortfolioRecord:
        """
        Retrieves a single portfolio by its ID.
        Raises an exception if the portfolio is not found.
        """
        logger.info(
            "Portfolio lookup requested.",
            extra=operation_log_extra(
                event_name="query.portfolio_service.lookup_requested",
                operation="query.portfolio_service.get_portfolio_by_id",
                status="started",
                reason_code="request_received",
            ),
        )
        db_portfolio = await self.repo.get_by_id(portfolio_id)
        if not db_portfolio:
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        return PortfolioRecord.model_validate(db_portfolio)
