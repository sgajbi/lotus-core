# services/query-service/app/services/price_service.py
import logging
from datetime import date
from typing import Optional

from portfolio_common.logging_utils import operation_log_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.collection_window_policy import validate_required_bounded_date_window
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
        validate_required_bounded_date_window(
            source_product="MarketPriceSeries",
            start_date=start_date,
            end_date=end_date,
        )
        logger.info(
            "Market price query requested.",
            extra=operation_log_extra(
                event_name="query.price_service.query_requested",
                operation="query.price_service.get_prices",
                status="started",
                reason_code="request_received",
                has_start_date_filter=start_date is not None,
                has_end_date_filter=end_date is not None,
            ),
        )
        security_id = normalize_security_id(security_id)

        db_results = await self.repo.get_prices(
            security_id=security_id, start_date=start_date, end_date=end_date
        )

        prices = [MarketPriceRecord.model_validate(row) for row in db_results]

        return MarketPriceResponse(security_id=security_id, prices=prices)
