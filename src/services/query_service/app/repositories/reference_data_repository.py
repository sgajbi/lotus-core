"""Persistence adapter for Query Service FX reference reads."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from portfolio_common.database_models import FxRate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.decimal_amounts import decimal_or_none
from .currency_codes import currency_code_sql_expr, normalize_currency_code


class ReferenceDataRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        from_currency_expr = currency_code_sql_expr(FxRate.from_currency)
        to_currency_expr = currency_code_sql_expr(FxRate.to_currency)
        stmt = (
            select(FxRate)
            .where(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date >= start_date,
                FxRate.rate_date <= end_date,
            )
            .order_by(FxRate.rate_date.asc())
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        rates: dict[date, Decimal] = {}
        for row in rows:
            rate = decimal_or_none(row.rate)
            if rate is not None:
                rates[row.rate_date] = rate
        return rates
