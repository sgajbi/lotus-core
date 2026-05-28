# services/query-service/app/services/price_service.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.price_dto import MarketPriceRecord, MarketPriceResponse
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.price_repository import MarketPriceRepository

logger = logging.getLogger(__name__)


class MarketPriceService:
    """
    Handles the business logic for querying market price data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = MarketPriceRepository(db)

    async def get_prices(
        self, security_id: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> MarketPriceResponse:
        """
        Retrieves a filtered list of market prices for a security.
        """
        logger.info(f"Fetching market prices for security '{security_id}'.")
        security_id = normalize_security_id(security_id)

        db_results = await self.repo.get_prices(
            security_id=security_id, start_date=start_date, end_date=end_date
        )

        prices = [MarketPriceRecord.model_validate(row) for row in db_results]

        return MarketPriceResponse(security_id=security_id, prices=prices)
