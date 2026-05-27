# services/query-service/app/services/fx_rate_service.py
import logging
from datetime import date
from typing import Optional

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
        logger.info(f"Fetching FX rates for '{from_currency}-{to_currency}'.")

        db_results = await self.repo.get_fx_rates(
            from_currency=from_currency,
            to_currency=to_currency,
            start_date=start_date,
            end_date=end_date,
        )

        rates = [FxRateRecord.model_validate(row) for row in db_results]

        return FxRateResponse(from_currency=from_currency, to_currency=to_currency, rates=rates)
