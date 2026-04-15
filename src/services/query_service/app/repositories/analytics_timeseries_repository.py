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
    PositionTimeseries,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsTimeseriesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

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
            partition_by.append(Cashflow.security_id)

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
            selected_columns.insert(1, Cashflow.security_id.label("security_id"))

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

    async def list_portfolio_observation_dates(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        snapshot_epoch: int | None = None,
    ) -> list[date]:
        predicates = [
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date >= start_date,
            PortfolioTimeseries.date <= end_date,
        ]
        if snapshot_epoch is not None:
            predicates.append(PortfolioTimeseries.epoch <= snapshot_epoch)
        ranked = (
            select(
                PortfolioTimeseries.date.label("valuation_date"),
                func.row_number()
                .over(
                    partition_by=PortfolioTimeseries.date,
                    order_by=(PortfolioTimeseries.epoch.desc(),),
                )
                .label("rn"),
            )
            .where(*predicates)
            .subquery()
        )
        stmt = (
            select(ranked.c.valuation_date)
            .where(ranked.c.rn == 1)
            .order_by(ranked.c.valuation_date.asc())
        )
        result = await self.db.execute(stmt)
        return [row.valuation_date for row in result.all()]

    async def list_portfolio_timeseries_rows(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        page_size: int,
        cursor_date: date | None,
        snapshot_epoch: int | None = None,
    ) -> list[Any]:
        predicates = [
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date >= start_date,
            PortfolioTimeseries.date <= end_date,
        ]
        if snapshot_epoch is not None:
            predicates.append(PortfolioTimeseries.epoch <= snapshot_epoch)
        ranked = (
            select(
                PortfolioTimeseries.date.label("valuation_date"),
                PortfolioTimeseries.bod_market_value.label("bod_market_value"),
                PortfolioTimeseries.eod_market_value.label("eod_market_value"),
                PortfolioTimeseries.bod_cashflow.label("bod_cashflow"),
                PortfolioTimeseries.eod_cashflow.label("eod_cashflow"),
                PortfolioTimeseries.fees.label("fees"),
                PortfolioTimeseries.epoch.label("epoch"),
                func.row_number()
                .over(
                    partition_by=PortfolioTimeseries.date,
                    order_by=(PortfolioTimeseries.epoch.desc(),),
                )
                .label("rn"),
            )
            .where(*predicates)
            .subquery()
        )

        stmt = select(ranked).where(ranked.c.rn == 1)
        if cursor_date is not None:
            stmt = stmt.where(ranked.c.valuation_date > cursor_date)
        stmt = stmt.order_by(ranked.c.valuation_date.asc()).limit(page_size + 1)

        result = await self.db.execute(stmt)
        return result.all()

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
        ranked = (
            select(
                PositionTimeseries.security_id.label("security_id"),
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
                    partition_by=(PositionTimeseries.security_id, PositionTimeseries.date),
                    order_by=(PositionTimeseries.epoch.desc(),),
                )
                .label("rn"),
            )
            .join(Instrument, Instrument.security_id == PositionTimeseries.security_id)
            .where(*predicates)
            .subquery()
        )

        stmt = select(ranked).where(ranked.c.rn == 1)

        if cursor_date is not None and cursor_security_id is not None:
            stmt = stmt.where(
                or_(
                    ranked.c.valuation_date > cursor_date,
                    and_(
                        ranked.c.valuation_date == cursor_date,
                        ranked.c.security_id > cursor_security_id,
                    ),
                )
            )

        if security_ids:
            stmt = stmt.where(ranked.c.security_id.in_(security_ids))

        if position_ids:
            security_from_position_ids = [
                pid.split(":", 1)[1]
                for pid in position_ids
                if ":" in pid and pid.split(":", 1)[0] == portfolio_id
            ]
            if security_from_position_ids:
                stmt = stmt.where(ranked.c.security_id.in_(security_from_position_ids))

        if "asset_class" in dimension_filters:
            stmt = stmt.where(ranked.c.asset_class.in_(dimension_filters["asset_class"]))
        if "sector" in dimension_filters:
            stmt = stmt.where(ranked.c.sector.in_(dimension_filters["sector"]))
        if "country" in dimension_filters:
            stmt = stmt.where(ranked.c.country.in_(dimension_filters["country"]))

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

        ranked = (
            select(
                PositionTimeseries.security_id.label("security_id"),
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
                Instrument.currency.label("position_currency"),
                func.row_number()
                .over(
                    partition_by=(PositionTimeseries.date, PositionTimeseries.security_id),
                    order_by=(PositionTimeseries.epoch.desc(),),
                )
                .label("rn"),
            )
            .join(Instrument, Instrument.security_id == PositionTimeseries.security_id)
            .where(*predicates)
            .subquery()
        )

        stmt = (
            select(ranked)
            .where(ranked.c.rn == 1)
            .order_by(ranked.c.valuation_date.asc(), ranked.c.security_id.asc())
        )
        result = await self.db.execute(stmt)
        return result.all()

    async def list_latest_position_timeseries_before(
        self,
        *,
        portfolio_id: str,
        before_date: date,
        security_ids: list[str],
        snapshot_epoch: int | None = None,
    ) -> list[Any]:
        if not security_ids:
            return []

        predicates = [
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id.in_(security_ids),
            PositionTimeseries.date < before_date,
        ]
        if snapshot_epoch is not None:
            predicates.append(PositionTimeseries.epoch <= snapshot_epoch)

        ranked = (
            select(
                PositionTimeseries.security_id.label("security_id"),
                PositionTimeseries.date.label("valuation_date"),
                PositionTimeseries.eod_market_value.label("eod_market_value"),
                PositionTimeseries.epoch.label("epoch"),
                func.row_number()
                .over(
                    partition_by=(PositionTimeseries.security_id,),
                    order_by=(PositionTimeseries.date.desc(), PositionTimeseries.epoch.desc()),
                )
                .label("rn"),
            )
            .where(*predicates)
            .subquery()
        )

        stmt = select(ranked).where(ranked.c.rn == 1).order_by(ranked.c.security_id.asc())
        result = await self.db.execute(stmt)
        return result.all()

    async def list_position_cashflow_rows(
        self,
        *,
        portfolio_id: str,
        security_ids: list[str],
        valuation_dates: list[date],
        snapshot_epoch: int | None = None,
    ) -> list[Any]:
        if not security_ids or not valuation_dates:
            return []

        predicates = [
            Cashflow.portfolio_id == portfolio_id,
            Cashflow.security_id.in_(security_ids),
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

    async def get_portfolio_snapshot_epoch(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> int:
        stmt = select(func.max(PortfolioTimeseries.epoch)).where(
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date >= start_date,
            PortfolioTimeseries.date <= end_date,
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one_or_none() or 0)

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
            .join(Instrument, Instrument.security_id == PositionTimeseries.security_id)
            .where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.date >= start_date,
                PositionTimeseries.date <= end_date,
            )
        )

        if security_ids:
            stmt = stmt.where(PositionTimeseries.security_id.in_(security_ids))

        if position_ids:
            security_from_position_ids = [
                pid.split(":", 1)[1]
                for pid in position_ids
                if ":" in pid and pid.split(":", 1)[0] == portfolio_id
            ]
            if security_from_position_ids:
                stmt = stmt.where(PositionTimeseries.security_id.in_(security_from_position_ids))

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
        stmt = (
            select(FxRate.rate_date, FxRate.rate)
            .where(
                FxRate.from_currency == from_currency,
                FxRate.to_currency == to_currency,
                FxRate.rate_date >= start_date,
                FxRate.rate_date <= end_date,
            )
            .order_by(FxRate.rate_date.asc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        return {row.rate_date: Decimal(row.rate) for row in rows}
