from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import (
    BenchmarkCompositionSeries,
    BenchmarkDefinition,
    BenchmarkReturnSeries,
    ClassificationTaxonomy,
    FxRate,
    IndexDefinition,
    IndexPriceSeries,
    IndexReturnSeries,
    PortfolioBenchmarkAssignment,
    RiskFreeSeries,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def _effective_filter(
    effective_from_column: Any,
    effective_to_column: Any,
    as_of_date: date,
):
    return and_(
        effective_from_column <= as_of_date,
        or_(effective_to_column.is_(None), effective_to_column >= as_of_date),
    )


class ReferenceDataRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def resolve_benchmark_assignment(self, portfolio_id: str, as_of_date: date):
        stmt = (
            select(PortfolioBenchmarkAssignment)
            .where(
                PortfolioBenchmarkAssignment.portfolio_id == portfolio_id,
                _effective_filter(
                    PortfolioBenchmarkAssignment.effective_from,
                    PortfolioBenchmarkAssignment.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                PortfolioBenchmarkAssignment.effective_from.desc(),
                PortfolioBenchmarkAssignment.assignment_recorded_at.desc(),
                PortfolioBenchmarkAssignment.assignment_version.desc(),
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def get_benchmark_definition(self, benchmark_id: str, as_of_date: date):
        stmt = (
            select(BenchmarkDefinition)
            .where(
                BenchmarkDefinition.benchmark_id == benchmark_id,
                _effective_filter(
                    BenchmarkDefinition.effective_from,
                    BenchmarkDefinition.effective_to,
                    as_of_date,
                ),
            )
            .order_by(BenchmarkDefinition.effective_from.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_benchmark_definitions_overlapping_window(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> list[BenchmarkDefinition]:
        stmt = (
            select(BenchmarkDefinition)
            .where(
                BenchmarkDefinition.benchmark_id == benchmark_id,
                BenchmarkDefinition.effective_from <= end_date,
                or_(
                    BenchmarkDefinition.effective_to.is_(None),
                    BenchmarkDefinition.effective_to >= start_date,
                ),
            )
            .order_by(BenchmarkDefinition.effective_from.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_definitions(
        self,
        as_of_date: date,
        benchmark_type: str | None = None,
        benchmark_currency: str | None = None,
        benchmark_status: str | None = None,
    ) -> list[BenchmarkDefinition]:
        stmt = select(BenchmarkDefinition).where(
            _effective_filter(
                BenchmarkDefinition.effective_from,
                BenchmarkDefinition.effective_to,
                as_of_date,
            )
        )
        if benchmark_type:
            stmt = stmt.where(BenchmarkDefinition.benchmark_type == benchmark_type)
        if benchmark_currency:
            stmt = stmt.where(BenchmarkDefinition.benchmark_currency == benchmark_currency.upper())
        if benchmark_status:
            stmt = stmt.where(BenchmarkDefinition.benchmark_status == benchmark_status)
        result = await self._db.execute(stmt.order_by(BenchmarkDefinition.benchmark_id.asc()))
        return list(result.scalars().all())

    async def list_index_definitions(
        self,
        as_of_date: date,
        index_currency: str | None = None,
        index_type: str | None = None,
        index_status: str | None = None,
    ) -> list[IndexDefinition]:
        stmt = select(IndexDefinition).where(
            _effective_filter(
                IndexDefinition.effective_from,
                IndexDefinition.effective_to,
                as_of_date,
            )
        )
        if index_currency:
            stmt = stmt.where(IndexDefinition.index_currency == index_currency.upper())
        if index_type:
            stmt = stmt.where(IndexDefinition.index_type == index_type)
        if index_status:
            stmt = stmt.where(IndexDefinition.index_status == index_status)
        result = await self._db.execute(stmt.order_by(IndexDefinition.index_id.asc()))
        return list(result.scalars().all())

    async def list_benchmark_components(
        self,
        benchmark_id: str,
        as_of_date: date,
    ) -> list[BenchmarkCompositionSeries]:
        stmt = (
            select(BenchmarkCompositionSeries)
            .where(
                BenchmarkCompositionSeries.benchmark_id == benchmark_id,
                _effective_filter(
                    BenchmarkCompositionSeries.composition_effective_from,
                    BenchmarkCompositionSeries.composition_effective_to,
                    as_of_date,
                ),
            )
            .order_by(BenchmarkCompositionSeries.index_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_components_overlapping_window(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> list[BenchmarkCompositionSeries]:
        stmt = (
            select(BenchmarkCompositionSeries)
            .where(
                BenchmarkCompositionSeries.benchmark_id == benchmark_id,
                BenchmarkCompositionSeries.composition_effective_from <= end_date,
                or_(
                    BenchmarkCompositionSeries.composition_effective_to.is_(None),
                    BenchmarkCompositionSeries.composition_effective_to >= start_date,
                ),
            )
            .order_by(
                BenchmarkCompositionSeries.composition_effective_from.asc(),
                BenchmarkCompositionSeries.index_id.asc(),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_components_for_benchmarks(
        self,
        benchmark_ids: list[str],
        as_of_date: date,
    ) -> dict[str, list[BenchmarkCompositionSeries]]:
        if not benchmark_ids:
            return {}

        stmt = (
            select(BenchmarkCompositionSeries)
            .where(
                BenchmarkCompositionSeries.benchmark_id.in_(benchmark_ids),
                _effective_filter(
                    BenchmarkCompositionSeries.composition_effective_from,
                    BenchmarkCompositionSeries.composition_effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                BenchmarkCompositionSeries.benchmark_id.asc(),
                BenchmarkCompositionSeries.index_id.asc(),
            )
        )
        rows = list((await self._db.execute(stmt)).scalars().all())
        grouped: dict[str, list[BenchmarkCompositionSeries]] = defaultdict(list)
        for row in rows:
            grouped[row.benchmark_id].append(row)
        return dict(grouped)

    async def list_index_price_points(
        self,
        index_ids: list[str],
        start_date: date,
        end_date: date,
    ) -> list[IndexPriceSeries]:
        if not index_ids:
            return []
        stmt = (
            select(IndexPriceSeries)
            .where(
                IndexPriceSeries.index_id.in_(index_ids),
                IndexPriceSeries.series_date >= start_date,
                IndexPriceSeries.series_date <= end_date,
            )
            .order_by(IndexPriceSeries.index_id.asc(), IndexPriceSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_return_points(
        self,
        index_ids: list[str],
        start_date: date,
        end_date: date,
    ) -> list[IndexReturnSeries]:
        if not index_ids:
            return []
        stmt = (
            select(IndexReturnSeries)
            .where(
                IndexReturnSeries.index_id.in_(index_ids),
                IndexReturnSeries.series_date >= start_date,
                IndexReturnSeries.series_date <= end_date,
            )
            .order_by(IndexReturnSeries.index_id.asc(), IndexReturnSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_return_points(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> list[BenchmarkReturnSeries]:
        stmt = (
            select(BenchmarkReturnSeries)
            .where(
                BenchmarkReturnSeries.benchmark_id == benchmark_id,
                BenchmarkReturnSeries.series_date >= start_date,
                BenchmarkReturnSeries.series_date <= end_date,
            )
            .order_by(BenchmarkReturnSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_price_series(
        self, index_id: str, start_date: date, end_date: date
    ) -> list[IndexPriceSeries]:
        stmt = (
            select(IndexPriceSeries)
            .where(
                IndexPriceSeries.index_id == index_id,
                IndexPriceSeries.series_date >= start_date,
                IndexPriceSeries.series_date <= end_date,
            )
            .order_by(IndexPriceSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_return_series(
        self, index_id: str, start_date: date, end_date: date
    ) -> list[IndexReturnSeries]:
        stmt = (
            select(IndexReturnSeries)
            .where(
                IndexReturnSeries.index_id == index_id,
                IndexReturnSeries.series_date >= start_date,
                IndexReturnSeries.series_date <= end_date,
            )
            .order_by(IndexReturnSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_risk_free_series(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> list[RiskFreeSeries]:
        stmt = (
            select(RiskFreeSeries)
            .where(
                RiskFreeSeries.series_currency == currency.upper(),
                RiskFreeSeries.series_date >= start_date,
                RiskFreeSeries.series_date <= end_date,
            )
            .order_by(RiskFreeSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> list[ClassificationTaxonomy]:
        stmt = select(ClassificationTaxonomy).where(
            _effective_filter(
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

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        components = await self.list_benchmark_components_overlapping_window(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
        )
        index_ids = sorted({row.index_id for row in components})
        price_points = await self.list_index_price_points(
            index_ids=index_ids,
            start_date=start_date,
            end_date=end_date,
        )
        benchmark_returns = await self.list_benchmark_return_points(
            benchmark_id,
            start_date,
            end_date,
        )
        total_points = len(price_points) + len(benchmark_returns)
        quality_counts: dict[str, int] = defaultdict(int)
        for row in price_points:
            quality_counts[row.quality_status] += 1
        for row in benchmark_returns:
            quality_counts[row.quality_status] += 1

        active_index_ids_by_date: dict[date, set[str]] = defaultdict(set)
        for component in components:
            component_start = max(
                getattr(component, "composition_effective_from", start_date),
                start_date,
            )
            component_end = min(
                getattr(component, "composition_effective_to", None) or end_date,
                end_date,
            )
            cursor = component_start
            while cursor <= component_end:
                active_index_ids_by_date[cursor].add(component.index_id)
                cursor = cursor + timedelta(days=1)

        price_index_ids_by_date: dict[date, set[str]] = defaultdict(set)
        for row in price_points:
            price_index_ids_by_date[row.series_date].add(row.index_id)

        benchmark_return_dates = {row.series_date for row in benchmark_returns}
        observed_dates = sorted(
            current_date
            for current_date, required_index_ids in active_index_ids_by_date.items()
            if required_index_ids
            and required_index_ids.issubset(price_index_ids_by_date.get(current_date, set()))
            and current_date in benchmark_return_dates
        )

        observed_start = min(observed_dates) if observed_dates else None
        observed_end = max(observed_dates) if observed_dates else None
        return {
            "total_points": total_points,
            "observed_start_date": observed_start,
            "observed_end_date": observed_end,
            "observed_dates": observed_dates,
            "quality_status_counts": dict(quality_counts),
        }

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        points = await self.list_risk_free_series(currency, start_date, end_date)
        all_dates = [row.series_date for row in points]
        quality_counts: dict[str, int] = defaultdict(int)
        for row in points:
            quality_counts[row.quality_status] += 1
        observed_start = min(all_dates) if all_dates else None
        observed_end = max(all_dates) if all_dates else None
        return {
            "total_points": len(points),
            "observed_start_date": observed_start,
            "observed_end_date": observed_end,
            "quality_status_counts": dict(quality_counts),
        }

    async def get_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        stmt = (
            select(FxRate)
            .where(
                FxRate.from_currency == from_currency.upper(),
                FxRate.to_currency == to_currency.upper(),
                FxRate.rate_date >= start_date,
                FxRate.rate_date <= end_date,
            )
            .order_by(FxRate.rate_date.asc())
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return {row.rate_date: Decimal(row.rate) for row in rows}
