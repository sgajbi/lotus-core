# services/query-service/app/repositories/fx_rate_repository.py
import logging
from datetime import date
from typing import List, Optional

from portfolio_common.database_models import FxRate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .currency_codes import normalize_currency_code

logger = logging.getLogger(__name__)


class FxRateRepository:
    """
    Handles read-only database queries for FX rate data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[FxRate]:
        """
        Retrieves a list of FX rates for a currency pair, with optional
        date range filtering.
        """
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        stmt = select(FxRate).filter_by(
            from_currency=normalized_from_currency, to_currency=normalized_to_currency
        )

        if start_date:
            stmt = stmt.filter(FxRate.rate_date >= start_date)

        if end_date:
            stmt = stmt.filter(FxRate.rate_date <= end_date)

        results = await self.db.execute(stmt.order_by(FxRate.rate_date.asc()))
        fx_rates = results.scalars().all()
        logger.info(
            "Found %s FX rates for '%s-%s' with given filters.",
            len(fx_rates),
            normalized_from_currency,
            normalized_to_currency,
        )
        return fx_rates
