from __future__ import annotations

from collections import defaultdict
from datetime import date
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
    RiskFreeSeries,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.decimal_amounts import decimal_or_none
from .currency_codes import currency_code_sql_expr, normalize_currency_code
from .reference_coverage_calculations import (
    latest_reference_evidence_timestamp,
    observed_benchmark_coverage_dates,
    quality_status_counts,
)
from .reference_data_query_helpers import (
    canonical_series_ranked_subquery,
    effective_filter,
    normalize_reference_status,
    ranked_latest_effective_ids,
)


class ReferenceDataRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_benchmark_definition(self, benchmark_id: str, as_of_date: date):
        stmt = (
            select(BenchmarkDefinition)
            .where(
                BenchmarkDefinition.benchmark_id == benchmark_id,
                effective_filter(
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
        predicates = [
            effective_filter(
                BenchmarkDefinition.effective_from,
                BenchmarkDefinition.effective_to,
                as_of_date,
            )
        ]
        if benchmark_type:
            predicates.append(BenchmarkDefinition.benchmark_type == benchmark_type)
        if benchmark_currency:
            predicates.append(
                BenchmarkDefinition.benchmark_currency
                == normalize_currency_code(benchmark_currency)
            )
        if benchmark_status:
            predicates.append(
                BenchmarkDefinition.benchmark_status == normalize_reference_status(benchmark_status)
            )

        ranked = ranked_latest_effective_ids(
            BenchmarkDefinition,
            BenchmarkDefinition.benchmark_id,
            predicates=predicates,
            order_by=(
                BenchmarkDefinition.effective_from.desc(),
                BenchmarkDefinition.source_timestamp.desc().nullslast(),
                BenchmarkDefinition.updated_at.desc(),
                BenchmarkDefinition.created_at.desc(),
                BenchmarkDefinition.id.desc(),
            ),
        )
        stmt = (
            select(BenchmarkDefinition)
            .join(ranked, BenchmarkDefinition.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkDefinition.benchmark_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_definitions(
        self,
        as_of_date: date,
        index_ids: list[str] | None = None,
        index_currency: str | None = None,
        index_type: str | None = None,
        index_status: str | None = None,
    ) -> list[IndexDefinition]:
        predicates = [
            effective_filter(
                IndexDefinition.effective_from,
                IndexDefinition.effective_to,
                as_of_date,
            )
        ]
        if index_ids:
            predicates.append(IndexDefinition.index_id.in_(index_ids))
        if index_currency:
            predicates.append(
                IndexDefinition.index_currency == normalize_currency_code(index_currency)
            )
        if index_type:
            predicates.append(IndexDefinition.index_type == index_type)
        if index_status:
            predicates.append(
                IndexDefinition.index_status == normalize_reference_status(index_status)
            )

        ranked = ranked_latest_effective_ids(
            IndexDefinition,
            IndexDefinition.index_id,
            predicates=predicates,
            order_by=(
                IndexDefinition.effective_from.desc(),
                IndexDefinition.source_timestamp.desc().nullslast(),
                IndexDefinition.updated_at.desc(),
                IndexDefinition.created_at.desc(),
                IndexDefinition.id.desc(),
            ),
        )
        stmt = (
            select(IndexDefinition)
            .join(ranked, IndexDefinition.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexDefinition.index_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_components(
        self,
        benchmark_id: str,
        as_of_date: date,
    ) -> list[BenchmarkCompositionSeries]:
        predicates = [
            BenchmarkCompositionSeries.benchmark_id == benchmark_id,
            effective_filter(
                BenchmarkCompositionSeries.composition_effective_from,
                BenchmarkCompositionSeries.composition_effective_to,
                as_of_date,
            ),
        ]
        ranked = ranked_latest_effective_ids(
            BenchmarkCompositionSeries,
            BenchmarkCompositionSeries.benchmark_id,
            BenchmarkCompositionSeries.index_id,
            predicates=predicates,
            order_by=(
                BenchmarkCompositionSeries.composition_effective_from.desc(),
                BenchmarkCompositionSeries.source_timestamp.desc().nullslast(),
                BenchmarkCompositionSeries.updated_at.desc(),
                BenchmarkCompositionSeries.created_at.desc(),
                BenchmarkCompositionSeries.id.desc(),
            ),
        )
        stmt = (
            select(BenchmarkCompositionSeries)
            .join(ranked, BenchmarkCompositionSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkCompositionSeries.index_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_components_overlapping_window(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
        index_ids: list[str] | None = None,
    ) -> list[BenchmarkCompositionSeries]:
        if index_ids is not None and not index_ids:
            return []

        stmt = select(BenchmarkCompositionSeries).where(
            BenchmarkCompositionSeries.benchmark_id == benchmark_id,
            BenchmarkCompositionSeries.composition_effective_from <= end_date,
            or_(
                BenchmarkCompositionSeries.composition_effective_to.is_(None),
                BenchmarkCompositionSeries.composition_effective_to >= start_date,
            ),
        )
        if index_ids:
            stmt = stmt.where(BenchmarkCompositionSeries.index_id.in_(index_ids))
        stmt = stmt.order_by(
            BenchmarkCompositionSeries.composition_effective_from.asc(),
            BenchmarkCompositionSeries.index_id.asc(),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_component_index_ids_overlapping_window(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
        *,
        after_index_id: str | None = None,
        limit: int | None = None,
    ) -> list[str]:
        stmt = (
            select(BenchmarkCompositionSeries.index_id)
            .distinct()
            .where(
                BenchmarkCompositionSeries.benchmark_id == benchmark_id,
                BenchmarkCompositionSeries.composition_effective_from <= end_date,
                or_(
                    BenchmarkCompositionSeries.composition_effective_to.is_(None),
                    BenchmarkCompositionSeries.composition_effective_to >= start_date,
                ),
            )
        )
        if after_index_id:
            stmt = stmt.where(BenchmarkCompositionSeries.index_id > after_index_id)
        stmt = stmt.order_by(BenchmarkCompositionSeries.index_id.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_benchmark_components_for_benchmarks(
        self,
        benchmark_ids: list[str],
        as_of_date: date,
    ) -> dict[str, list[BenchmarkCompositionSeries]]:
        if not benchmark_ids:
            return {}

        predicates = [
            BenchmarkCompositionSeries.benchmark_id.in_(benchmark_ids),
            effective_filter(
                BenchmarkCompositionSeries.composition_effective_from,
                BenchmarkCompositionSeries.composition_effective_to,
                as_of_date,
            ),
        ]
        ranked = ranked_latest_effective_ids(
            BenchmarkCompositionSeries,
            BenchmarkCompositionSeries.benchmark_id,
            BenchmarkCompositionSeries.index_id,
            predicates=predicates,
            order_by=(
                BenchmarkCompositionSeries.composition_effective_from.desc(),
                BenchmarkCompositionSeries.source_timestamp.desc().nullslast(),
                BenchmarkCompositionSeries.updated_at.desc(),
                BenchmarkCompositionSeries.created_at.desc(),
                BenchmarkCompositionSeries.id.desc(),
            ),
        )
        stmt = (
            select(BenchmarkCompositionSeries)
            .join(ranked, BenchmarkCompositionSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
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
        predicates = (
            IndexPriceSeries.index_id.in_(index_ids),
            IndexPriceSeries.series_date >= start_date,
            IndexPriceSeries.series_date <= end_date,
        )
        ranked = canonical_series_ranked_subquery(
            IndexPriceSeries,
            IndexPriceSeries.index_id,
            IndexPriceSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(IndexPriceSeries)
            .join(ranked, IndexPriceSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
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
        predicates = (
            IndexReturnSeries.index_id.in_(index_ids),
            IndexReturnSeries.series_date >= start_date,
            IndexReturnSeries.series_date <= end_date,
        )
        ranked = canonical_series_ranked_subquery(
            IndexReturnSeries,
            IndexReturnSeries.index_id,
            IndexReturnSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(IndexReturnSeries)
            .join(ranked, IndexReturnSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
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
        predicates = (
            BenchmarkReturnSeries.benchmark_id == benchmark_id,
            BenchmarkReturnSeries.series_date >= start_date,
            BenchmarkReturnSeries.series_date <= end_date,
        )
        ranked = canonical_series_ranked_subquery(
            BenchmarkReturnSeries,
            BenchmarkReturnSeries.benchmark_id,
            BenchmarkReturnSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(BenchmarkReturnSeries)
            .join(ranked, BenchmarkReturnSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(BenchmarkReturnSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_price_series(
        self, index_id: str, start_date: date, end_date: date
    ) -> list[IndexPriceSeries]:
        predicates = (
            IndexPriceSeries.index_id == index_id,
            IndexPriceSeries.series_date >= start_date,
            IndexPriceSeries.series_date <= end_date,
        )
        ranked = canonical_series_ranked_subquery(
            IndexPriceSeries,
            IndexPriceSeries.index_id,
            IndexPriceSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(IndexPriceSeries)
            .join(ranked, IndexPriceSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(IndexPriceSeries.series_date.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_index_return_series(
        self, index_id: str, start_date: date, end_date: date
    ) -> list[IndexReturnSeries]:
        predicates = (
            IndexReturnSeries.index_id == index_id,
            IndexReturnSeries.series_date >= start_date,
            IndexReturnSeries.series_date <= end_date,
        )
        ranked = canonical_series_ranked_subquery(
            IndexReturnSeries,
            IndexReturnSeries.index_id,
            IndexReturnSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(IndexReturnSeries)
            .join(ranked, IndexReturnSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
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
        predicates = (
            RiskFreeSeries.series_currency == normalize_currency_code(currency),
            RiskFreeSeries.series_date >= start_date,
            RiskFreeSeries.series_date <= end_date,
        )
        ranked = canonical_series_ranked_subquery(
            RiskFreeSeries,
            RiskFreeSeries.series_date,
            predicates=predicates,
        )
        stmt = (
            select(RiskFreeSeries)
            .join(ranked, RiskFreeSeries.id == ranked.c.id)
            .where(ranked.c.rn == 1)
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
        observed_dates = observed_benchmark_coverage_dates(
            components=components,
            price_points=price_points,
            benchmark_returns=benchmark_returns,
            start_date=start_date,
            end_date=end_date,
        )
        total_points = len(price_points) + len(benchmark_returns)
        observed_start = min(observed_dates) if observed_dates else None
        observed_end = max(observed_dates) if observed_dates else None
        coverage_rows = price_points + benchmark_returns
        return {
            "total_points": total_points,
            "observed_start_date": observed_start,
            "observed_end_date": observed_end,
            "observed_dates": observed_dates,
            "quality_status_counts": quality_status_counts(coverage_rows),
            "latest_evidence_timestamp": latest_reference_evidence_timestamp(coverage_rows),
        }

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        points = await self.list_risk_free_series(currency, start_date, end_date)
        all_dates = [row.series_date for row in points]
        observed_start = min(all_dates) if all_dates else None
        observed_end = max(all_dates) if all_dates else None
        return {
            "total_points": len(points),
            "observed_start_date": observed_start,
            "observed_end_date": observed_end,
            "quality_status_counts": quality_status_counts(points),
            "observed_dates": all_dates,
            "latest_evidence_timestamp": latest_reference_evidence_timestamp(points),
        }

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
