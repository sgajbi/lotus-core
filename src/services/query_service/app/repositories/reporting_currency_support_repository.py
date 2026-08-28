from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import cast

from portfolio_common.database_models import (
    FxRate,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    PositionTimeseries,
)
from portfolio_common.domain.currency import normalize_currency_code
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .currency_query_expressions import currency_code_sql_expr


@dataclass(frozen=True, slots=True)
class PortfolioCurrencySource:
    tenant_id: str | None
    base_currency: str
    source_currencies: tuple[str, ...]


class ReportingCurrencySupportRepository:
    """Read source-owned portfolio and FX evidence for supportability decisions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_portfolio_currency_source(
        self,
        *,
        portfolio_id: str,
        tenant_id: str | None,
        as_of_date: date,
    ) -> PortfolioCurrencySource | None:
        portfolio_stmt = select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
        if tenant_id is not None:
            portfolio_stmt = portfolio_stmt.where(Portfolio.tenant_id == tenant_id)
        portfolio = (await self.db.execute(portfolio_stmt)).scalar_one_or_none()
        if portfolio is None:
            return None
        if as_of_date < portfolio.open_date:
            raise ValueError("as_of_date precedes portfolio inception")

        history_security_id = func.trim(PositionHistory.security_id)
        state_security_id = func.trim(PositionState.security_id)
        latest_positions = (
            select(
                history_security_id.label("security_id"),
                PositionHistory.epoch.label("epoch"),
                PositionHistory.quantity.label("quantity"),
                func.row_number()
                .over(
                    partition_by=history_security_id,
                    order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionHistory.portfolio_id == PositionState.portfolio_id,
                    history_security_id == state_security_id,
                    PositionHistory.epoch == PositionState.epoch,
                ),
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.position_date <= as_of_date,
            )
            .subquery()
        )
        instrument_currency = currency_code_sql_expr(Instrument.currency)
        currency_stmt = (
            select(instrument_currency.label("source_currency"))
            .select_from(latest_positions)
            .outerjoin(
                Instrument,
                func.trim(Instrument.security_id) == latest_positions.c.security_id,
            )
            .where(
                latest_positions.c.rn == 1,
                or_(
                    latest_positions.c.quantity != 0,
                    exists(
                        select(1).where(
                            PositionTimeseries.portfolio_id == portfolio_id,
                            func.trim(PositionTimeseries.security_id)
                            == latest_positions.c.security_id,
                            PositionTimeseries.date == as_of_date,
                            PositionTimeseries.epoch == latest_positions.c.epoch,
                            PositionTimeseries.quantity == latest_positions.c.quantity,
                        )
                    ),
                ),
            )
            .distinct()
            .order_by(instrument_currency.asc())
        )
        currencies = list((await self.db.execute(currency_stmt)).scalars().all())
        for currency in currencies:
            if currency is None or not str(currency).strip():
                raise ValueError("position source currency is unavailable")
        normalized_base = normalize_currency_code(portfolio.base_currency)
        source_currencies = tuple(
            sorted({normalized_base, *(normalize_currency_code(c) for c in currencies)})
        )
        return PortfolioCurrencySource(
            tenant_id=portfolio.tenant_id,
            base_currency=normalized_base,
            source_currencies=source_currencies,
        )

    async def get_latest_fx_rate_dates(
        self,
        *,
        from_currencies: tuple[str, ...],
        to_currency: str,
        as_of_date: date,
    ) -> dict[str, date]:
        """Return all latest as-of FX dates in one bounded query."""
        normalized_sources = tuple(normalize_currency_code(value) for value in from_currencies)
        normalized_target = normalize_currency_code(to_currency)
        if not normalized_sources:
            return {}
        stmt = (
            select(
                currency_code_sql_expr(FxRate.from_currency).label("from_currency"),
                func.max(FxRate.rate_date).label("rate_date"),
            )
            .where(
                currency_code_sql_expr(FxRate.from_currency).in_(normalized_sources),
                currency_code_sql_expr(FxRate.to_currency) == normalized_target,
                FxRate.rate_date == as_of_date,
            )
            .group_by(currency_code_sql_expr(FxRate.from_currency))
        )
        rows = (await self.db.execute(stmt)).all()
        return {
            str(from_currency): cast(date, rate_date)
            for from_currency, rate_date in rows
            if rate_date is not None
        }

    async def is_selector_currency_observed(self, *, currency: str) -> bool:
        code = normalize_currency_code(currency)
        portfolio_match = (
            select(Portfolio.portfolio_id)
            .where(currency_code_sql_expr(Portfolio.base_currency) == code)
            .limit(1)
        )
        if (await self.db.execute(portfolio_match)).scalar_one_or_none() is not None:
            return True
        instrument_match = (
            select(Instrument.security_id)
            .where(currency_code_sql_expr(Instrument.currency) == code)
            .limit(1)
        )
        return (await self.db.execute(instrument_match)).scalar_one_or_none() is not None
