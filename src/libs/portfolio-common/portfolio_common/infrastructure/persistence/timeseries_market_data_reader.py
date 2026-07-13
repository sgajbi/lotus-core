"""Shared market/reference reads used by timeseries processing services."""

from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import FxRate, Instrument
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.market_data.timeseries import (
    TimeseriesFxRate,
    TimeseriesInstrument,
)
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.utils import async_timed


class TimeseriesMarketDataReader:
    """Read instrument and FX inputs shared by timeseries processing services."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="TimeseriesRepository", method="get_instruments_by_ids")
    async def get_instruments_by_ids(
        self,
        security_ids: list[str],
    ) -> list[TimeseriesInstrument]:
        normalized_security_ids = [
            normalized
            for security_id in security_ids
            if (normalized := normalize_lookup_identifier(security_id))
        ]
        if not normalized_security_ids:
            return []
        result = await self.db.execute(
            select(Instrument).where(func.trim(Instrument.security_id).in_(normalized_security_ids))
        )
        rows = cast(list[Instrument], result.scalars().all())
        return [
            TimeseriesInstrument(security_id=str(row.security_id), currency=str(row.currency))
            for row in rows
        ]

    @async_timed(repository="TimeseriesRepository", method="get_fx_rate")
    async def get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        a_date: date,
    ) -> TimeseriesFxRate | None:
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        from_currency_expr = func.upper(func.trim(FxRate.from_currency))
        to_currency_expr = func.upper(func.trim(FxRate.to_currency))
        result = await self.db.execute(
            select(FxRate)
            .where(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date <= a_date,
            )
            .order_by(FxRate.rate_date.desc())
        )
        row = result.scalars().first()
        if row is None:
            return None
        return TimeseriesFxRate(rate=cast(Decimal, row.rate))
