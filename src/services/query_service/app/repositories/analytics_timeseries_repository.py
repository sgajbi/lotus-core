from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    Cashflow,
    FxRate,
    Instrument,
    Portfolio,
    PortfolioTimeseries,
    PositionHistory,
    PositionState,
    PositionTimeseries,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.decimal_amounts import decimal_or_none
from .currency_codes import currency_code_sql_expr, normalize_currency_code
from .identifier_normalization import normalize_security_id

DIMENSION_FILTER_COLUMNS = {
    "asset_class": "asset_class",
    "sector": "sector",
    "country": "country",
}


def _position_page_cursor_filter(ranked, cursor_date: date | None, cursor_security_id: str | None):
    if cursor_date is None or cursor_security_id is None:
        return None
    return or_(
        ranked.c.valuation_date > cursor_date,
        and_(
            ranked.c.valuation_date == cursor_date,
            ranked.c.security_id > cursor_security_id,
        ),
    )


def _position_dimension_filters(ranked, dimension_filters: dict[str, set[str]]) -> list[object]:
    return [
        getattr(ranked.c, column_name).in_(dimension_filters[dimension_name])
        for dimension_name, column_name in DIMENSION_FILTER_COLUMNS.items()
        if dimension_name in dimension_filters
    ]


def _append_optional_where(stmt, predicate):
    return stmt.where(predicate) if predicate is not None else stmt


class AnalyticsTimeseriesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _normalized_security_ids(security_ids: list[str]) -> list[str]:
        normalized_security_ids = [
            normalized
            for security_id in security_ids
            if (normalized := normalize_security_id(security_id))
        ]
        return list(dict.fromkeys(normalized_security_ids))

    @staticmethod
    def _security_ids_from_position_ids(portfolio_id: str, position_ids: list[str]) -> list[str]:
        normalized_security_ids = [
            normalized
            for position_id in position_ids
            if ":" in position_id
            and position_id.split(":", 1)[0] == portfolio_id
            and (normalized := normalize_security_id(position_id.split(":", 1)[1]))
        ]
        return list(dict.fromkeys(normalized_security_ids))

    def _security_scope_filter(self, ranked, security_ids: list[str]):
        if not security_ids:
            return True, None
        normalized_security_ids = self._normalized_security_ids(security_ids)
        if not normalized_security_ids:
            return False, None
        return True, ranked.c.security_id.in_(normalized_security_ids)

    def _position_scope_filter(self, ranked, portfolio_id: str, position_ids: list[str]):
        if not position_ids:
            return True, None
        security_from_position_ids = self._security_ids_from_position_ids(
            portfolio_id, position_ids
        )
        if not security_from_position_ids:
            return False, None
        return True, ranked.c.security_id.in_(security_from_position_ids)

    @staticmethod
    def _latest_cashflow_rows_stmt(*, predicates: list[object], include_security_id: bool):
        partition_by = [
            Cashflow.transaction_id,
            Cashflow.cashflow_date,
            Cashflow.classification,
            Cashflow.timing,
            Cashflow.is_position_flow,
            Cashflow.is_portfolio_flow,
        ]
        if include_security_id:
            partition_by.append(func.trim(Cashflow.security_id))

        selected_columns = [
            Cashflow.transaction_id.label("transaction_id"),
            Cashflow.cashflow_date.label("valuation_date"),
            Cashflow.amount.label("amount"),
            Cashflow.currency.label("currency"),
            Cashflow.classification.label("classification"),
            Cashflow.timing.label("timing"),
            Cashflow.is_position_flow.label("is_position_flow"),
            Cashflow.is_portfolio_flow.label("is_portfolio_flow"),
            Cashflow.epoch.label("epoch"),
            func.row_number()
            .over(
                partition_by=tuple(partition_by),
                order_by=(Cashflow.epoch.desc(),),
            )
            .label("rn"),
        ]
        if include_security_id:
            selected_columns.insert(1, func.trim(Cashflow.security_id).label("security_id"))

        ranked = select(*selected_columns).where(*predicates).subquery()

        ordering = [ranked.c.valuation_date.asc()]
        if include_security_id:
            ordering.append(ranked.c.security_id.asc())
        ordering.extend([ranked.c.timing.asc(), ranked.c.transaction_id.asc()])

        return select(ranked).where(ranked.c.rn == 1).order_by(*ordering)

    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        stmt = select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_latest_portfolio_timeseries_date(self, portfolio_id: str) -> date | None:
        stmt = select(func.max(PortfolioTimeseries.date)).where(
            PortfolioTimeseries.portfolio_id == portfolio_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_position_timeseries_date(self, portfolio_id: str) -> date | None:
        stmt = select(func.max(PositionTimeseries.date)).where(
            PositionTimeseries.portfolio_id == portfolio_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_business_dates(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        stmt = (
            select(BusinessDate.date)
            .where(
                BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE,
                BusinessDate.date >= start_date,
                BusinessDate.date <= end_date,
            )
            .order_by(BusinessDate.date.asc())
        )
        result = await self.db.execute(stmt)
        return [row.date for row in result.all()]

    async def list_position_timeseries_rows(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        page_size: int,
        cursor_date: date | None,
        cursor_security_id: str | None,
        security_ids: list[str],
        position_ids: list[str],
        dimension_filters: dict[str, set[str]],
        snapshot_epoch: int | None = None,
    ) -> list[Any]:
        predicates = [
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.date >= start_date,
            PositionTimeseries.date <= end_date,
        ]
        if snapshot_epoch is not None:
            predicates.append(PositionTimeseries.epoch <= snapshot_epoch)
        latest_history_quantity = self._latest_current_position_history_quantity()
        position_security_id = func.trim(PositionTimeseries.security_id)
        state_security_id = func.trim(PositionState.security_id)
        instrument_security_id = func.trim(Instrument.security_id)
        ranked = (
            select(
                position_security_id.label("security_id"),
                PositionTimeseries.date.label("valuation_date"),
                PositionTimeseries.bod_market_value.label("bod_market_value"),
                PositionTimeseries.eod_market_value.label("eod_market_value"),
                PositionTimeseries.bod_cashflow_position.label("bod_cashflow_position"),
                PositionTimeseries.eod_cashflow_position.label("eod_cashflow_position"),
                PositionTimeseries.bod_cashflow_portfolio.label("bod_cashflow_portfolio"),
                PositionTimeseries.eod_cashflow_portfolio.label("eod_cashflow_portfolio"),
                PositionTimeseries.fees.label("fees"),
                PositionTimeseries.quantity.label("quantity"),
                PositionTimeseries.epoch.label("epoch"),
                Instrument.asset_class.label("asset_class"),
                Instrument.sector.label("sector"),
                Instrument.country_of_risk.label("country"),
                Instrument.currency.label("position_currency"),
                func.row_number()
                .over(
                    partition_by=(position_security_id, PositionTimeseries.date),
                    order_by=(PositionTimeseries.epoch.desc(),),
                )
                .label("rn"),
            )
            .select_from(PositionTimeseries)
            .join(
                PositionState,
                and_(
                    PositionTimeseries.portfolio_id == PositionState.portfolio_id,
                    position_security_id == state_security_id,
                    PositionTimeseries.epoch == PositionState.epoch,
                ),
            )
            .join(Instrument, instrument_security_id == position_security_id)
            .where(*predicates, PositionTimeseries.quantity == latest_history_quantity)
            .subquery()
        )

        stmt = select(ranked).where(ranked.c.rn == 1)

        stmt = _append_optional_where(
            stmt,
            _position_page_cursor_filter(ranked, cursor_date, cursor_security_id),
        )
        for is_supported, predicate in (
            self._security_scope_filter(ranked, security_ids),
            self._position_scope_filter(ranked, portfolio_id, position_ids),
        ):
            if not is_supported:
                return []
            stmt = _append_optional_where(stmt, predicate)
        for predicate in _position_dimension_filters(ranked, dimension_filters):
            stmt = stmt.where(predicate)

        stmt = stmt.order_by(ranked.c.valuation_date.asc(), ranked.c.security_id.asc()).limit(
            page_size + 1
        )
        result = await self.db.execute(stmt)
        return result.all()

    async def list_position_timeseries_rows_unpaged(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        snapshot_epoch: int | None = None,
    ) -> list[Any]:
        predicates = [
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.date >= start_date,
            PositionTimeseries.date <= end_date,
        ]
        if snapshot_epoch is not None:
            predicates.append(PositionTimeseries.epoch <= snapshot_epoch)

        latest_history_quantity = self._latest_current_position_history_quantity()
        position_security_id = func.trim(PositionTimeseries.security_id)
        state_security_id = func.trim(PositionState.security_id)
        instrument_security_id = func.trim(Instrument.security_id)
        ranked = (
            select(
                position_security_id.label("security_id"),
                PositionTimeseries.date.label("valuation_date"),
                PositionTimeseries.bod_market_value.label("bod_market_value"),
                PositionTimeseries.eod_market_value.label("eod_market_value"),
                PositionTimeseries.bod_cashflow_position.label("bod_cashflow_position"),
                PositionTimeseries.eod_cashflow_position.label("eod_cashflow_position"),
                PositionTimeseries.bod_cashflow_portfolio.label("bod_cashflow_portfolio"),
                PositionTimeseries.eod_cashflow_portfolio.label("eod_cashflow_portfolio"),
                PositionTimeseries.fees.label("fees"),
                PositionTimeseries.quantity.label("quantity"),
                PositionTimeseries.epoch.label("epoch"),
                Instrument.asset_class.label("asset_class"),
                Instrument.currency.label("position_currency"),
                func.row_number()
                .over(
                    partition_by=(PositionTimeseries.date, position_security_id),
                    order_by=(PositionTimeseries.epoch.desc(),),
                )
                .label("rn"),
            )
            .select_from(PositionTimeseries)
            .join(
                PositionState,
                and_(
                    PositionTimeseries.portfolio_id == PositionState.portfolio_id,
                    position_security_id == state_security_id,
                    PositionTimeseries.epoch == PositionState.epoch,
                ),
            )
            .join(Instrument, instrument_security_id == position_security_id)
            .where(*predicates, PositionTimeseries.quantity == latest_history_quantity)
            .subquery()
        )

        stmt = (
            select(ranked)
            .where(ranked.c.rn == 1)
            .order_by(ranked.c.valuation_date.asc(), ranked.c.security_id.asc())
        )
        result = await self.db.execute(stmt)
        return result.all()

    async def list_position_observation_dates(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        snapshot_epoch: int | None = None,
    ) -> list[date]:
        predicates = [
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.date >= start_date,
            PositionTimeseries.date <= end_date,
        ]
        if snapshot_epoch is not None:
            predicates.append(PositionTimeseries.epoch <= snapshot_epoch)

        latest_history_quantity = self._latest_current_position_history_quantity()
        position_security_id = func.trim(PositionTimeseries.security_id)
        state_security_id = func.trim(PositionState.security_id)
        ranked = (
            select(
                PositionTimeseries.date.label("valuation_date"),
                func.row_number()
                .over(
                    partition_by=(PositionTimeseries.date, position_security_id),
                    order_by=(PositionTimeseries.epoch.desc(),),
                )
                .label("rn"),
            )
            .select_from(PositionTimeseries)
            .join(
                PositionState,
                and_(
                    PositionTimeseries.portfolio_id == PositionState.portfolio_id,
                    position_security_id == state_security_id,
                    PositionTimeseries.epoch == PositionState.epoch,
                ),
            )
            .where(*predicates, PositionTimeseries.quantity == latest_history_quantity)
            .subquery()
        )

        stmt = (
            select(ranked.c.valuation_date)
            .where(ranked.c.rn == 1)
            .distinct()
            .order_by(ranked.c.valuation_date.asc())
        )
        result = await self.db.execute(stmt)
        return [row.valuation_date for row in result.all()]

    async def list_latest_position_timeseries_before(
        self,
        *,
        portfolio_id: str,
        before_date: date,
        security_ids: list[str],
        snapshot_epoch: int | None = None,
    ) -> list[Any]:
        normalized_security_ids = self._normalized_security_ids(security_ids)
        if not normalized_security_ids:
            return []

        position_security_id = func.trim(PositionTimeseries.security_id)
        state_security_id = func.trim(PositionState.security_id)
        predicates = [
            PositionTimeseries.portfolio_id == portfolio_id,
            position_security_id.in_(normalized_security_ids),
            PositionTimeseries.date < before_date,
        ]
        if snapshot_epoch is not None:
            predicates.append(PositionTimeseries.epoch <= snapshot_epoch)

        latest_history_quantity = self._latest_current_position_history_quantity()
        ranked = (
            select(
                position_security_id.label("security_id"),
                PositionTimeseries.date.label("valuation_date"),
                PositionTimeseries.eod_market_value.label("eod_market_value"),
                PositionTimeseries.epoch.label("epoch"),
                func.row_number()
                .over(
                    partition_by=(position_security_id,),
                    order_by=(PositionTimeseries.date.desc(), PositionTimeseries.epoch.desc()),
                )
                .label("rn"),
            )
            .select_from(PositionTimeseries)
            .join(
                PositionState,
                and_(
                    PositionTimeseries.portfolio_id == PositionState.portfolio_id,
                    position_security_id == state_security_id,
                    PositionTimeseries.epoch == PositionState.epoch,
                ),
            )
            .where(*predicates, PositionTimeseries.quantity == latest_history_quantity)
            .subquery()
        )

        stmt = select(ranked).where(ranked.c.rn == 1).order_by(ranked.c.security_id.asc())
        result = await self.db.execute(stmt)
        return result.all()

    @staticmethod
    def _latest_current_position_history_quantity():
        return (
            select(PositionHistory.quantity)
            .where(
                PositionHistory.portfolio_id == PositionTimeseries.portfolio_id,
                func.trim(PositionHistory.security_id) == func.trim(PositionTimeseries.security_id),
                PositionHistory.epoch == PositionState.epoch,
                PositionHistory.position_date <= PositionTimeseries.date,
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
            .limit(1)
            .correlate(PositionTimeseries, PositionState)
            .scalar_subquery()
        )

    async def list_position_cashflow_rows(
        self,
        *,
        portfolio_id: str,
        security_ids: list[str],
        valuation_dates: list[date],
        snapshot_epoch: int | None = None,
    ) -> list[Any]:
        normalized_security_ids = self._normalized_security_ids(security_ids)
        if not normalized_security_ids or not valuation_dates:
            return []

        predicates = [
            Cashflow.portfolio_id == portfolio_id,
            func.trim(Cashflow.security_id).in_(normalized_security_ids),
            Cashflow.cashflow_date.in_(valuation_dates),
            Cashflow.is_position_flow.is_(True),
        ]
        if snapshot_epoch is not None:
            predicates.append(Cashflow.epoch <= snapshot_epoch)

        stmt = self._latest_cashflow_rows_stmt(predicates=predicates, include_security_id=True)
        result = await self.db.execute(stmt)
        return result.all()

    async def list_portfolio_cashflow_rows(
        self,
        *,
        portfolio_id: str,
        valuation_dates: list[date],
        snapshot_epoch: int | None = None,
    ) -> list[Any]:
        if not valuation_dates:
            return []

        predicates = [
            Cashflow.portfolio_id == portfolio_id,
            Cashflow.cashflow_date.in_(valuation_dates),
            Cashflow.is_portfolio_flow.is_(True),
        ]
        if snapshot_epoch is not None:
            predicates.append(Cashflow.epoch <= snapshot_epoch)

        stmt = self._latest_cashflow_rows_stmt(predicates=predicates, include_security_id=False)
        result = await self.db.execute(stmt)
        return result.all()

    async def get_position_snapshot_epoch(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        security_ids: list[str],
        position_ids: list[str],
        dimension_filters: dict[str, set[str]],
    ) -> int:
        stmt = (
            select(func.max(PositionTimeseries.epoch))
            .select_from(PositionTimeseries)
            .join(
                Instrument,
                func.trim(Instrument.security_id) == func.trim(PositionTimeseries.security_id),
            )
            .where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.date >= start_date,
                PositionTimeseries.date <= end_date,
            )
        )

        if security_ids:
            normalized_security_ids = self._normalized_security_ids(security_ids)
            if not normalized_security_ids:
                return 0
            stmt = stmt.where(
                func.trim(PositionTimeseries.security_id).in_(normalized_security_ids)
            )

        if position_ids:
            security_from_position_ids = self._security_ids_from_position_ids(
                portfolio_id, position_ids
            )
            if not security_from_position_ids:
                return 0
            stmt = stmt.where(
                func.trim(PositionTimeseries.security_id).in_(security_from_position_ids)
            )

        if "asset_class" in dimension_filters:
            stmt = stmt.where(Instrument.asset_class.in_(dimension_filters["asset_class"]))
        if "sector" in dimension_filters:
            stmt = stmt.where(Instrument.sector.in_(dimension_filters["sector"]))
        if "country" in dimension_filters:
            stmt = stmt.where(Instrument.country_of_risk.in_(dimension_filters["country"]))

        result = await self.db.execute(stmt)
        return int(result.scalar_one_or_none() or 0)

    async def get_fx_rates_map(
        self,
        *,
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
            select(FxRate.rate_date, FxRate.rate)
            .where(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date >= start_date,
                FxRate.rate_date <= end_date,
            )
            .order_by(FxRate.rate_date.asc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        rates: dict[date, Decimal] = {}
        for row in rows:
            rate = decimal_or_none(row.rate)
            if rate is not None:
                rates[row.rate_date] = rate
        return rates
