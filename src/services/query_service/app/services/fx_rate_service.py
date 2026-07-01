# services/query-service/app/services/fx_rate_service.py
import logging
from datetime import date
from typing import Optional

from portfolio_common.logging_utils import operation_log_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.fx_rate_dto import FxRateRecord, FxRateResponse
from ..repositories.fx_rate_repository import FxRateRepository

logger = logging.getLogger(__name__)


class FxRateService:
    """
    Handles the business logic for querying FX rate data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = FxRateRepository(db)

    async def get_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> FxRateResponse:
        """
        Retrieves a filtered list of FX rates for a currency pair.
        """
        logger.info(
            "FX rate query requested.",
            extra=operation_log_extra(
                event_name="query.fx_rate_service.query_requested",
                operation="query.fx_rate_service.get_fx_rates",
                status="started",
                reason_code="request_received",
                has_start_date_filter=start_date is not None,
                has_end_date_filter=end_date is not None,
            ),
        )

        db_results = await self.repo.get_fx_rates(
            from_currency=from_currency,
            to_currency=to_currency,
            start_date=start_date,
            end_date=end_date,
        )

        rates = [FxRateRecord.model_validate(row) for row in db_results]

        return FxRateResponse(from_currency=from_currency, to_currency=to_currency, rates=rates)
