"""Persistence adapter for Query Service taxonomy and FX reference reads."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from portfolio_common.database_models import (
    ClassificationTaxonomy,
    FxRate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.decimal_amounts import decimal_or_none
from .currency_codes import currency_code_sql_expr, normalize_currency_code
from .reference_data_query_helpers import (
    effective_filter,
)


class ReferenceDataRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> list[ClassificationTaxonomy]:
        stmt = select(ClassificationTaxonomy).where(
            effective_filter(
                ClassificationTaxonomy.effective_from,
                ClassificationTaxonomy.effective_to,
                as_of_date,
            )
        )
        if taxonomy_scope:
            stmt = stmt.where(ClassificationTaxonomy.taxonomy_scope == taxonomy_scope)
        result = await self._db.execute(
            stmt.order_by(
                ClassificationTaxonomy.taxonomy_scope.asc(),
                ClassificationTaxonomy.dimension_name.asc(),
                ClassificationTaxonomy.dimension_value.asc(),
            )
        )
        return list(result.scalars().all())

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
