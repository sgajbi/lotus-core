# services/query-service/app/services/portfolio_service.py
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

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
            "Fetching portfolios with filters: "
            f"portfolio_id={portfolio_id}, portfolio_ids={portfolio_ids}, "
            f"client_id={client_id}, booking_center_code={booking_center_code}"
        )

        db_results = await self.repo.get_portfolios(
            portfolio_id=portfolio_id,
            portfolio_ids=portfolio_ids,
            client_id=client_id,
            booking_center_code=booking_center_code,
        )

        portfolios = [PortfolioRecord.model_validate(p) for p in db_results]

        return PortfolioQueryResponse(portfolios=portfolios)

    async def get_portfolio_by_id(self, portfolio_id: str) -> PortfolioRecord:
        """
        Retrieves a single portfolio by its ID.
        Raises an exception if the portfolio is not found.
        """
        logger.info(f"Fetching portfolio with id: {portfolio_id}")
        db_portfolio = await self.repo.get_by_id(portfolio_id)
        if not db_portfolio:
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        return PortfolioRecord.model_validate(db_portfolio)

