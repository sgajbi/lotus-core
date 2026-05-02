from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
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
    MarketPrice,
    InstrumentEligibilityProfile,
    ModelPortfolioDefinition,
    ModelPortfolioTarget,
    PortfolioBenchmarkAssignment,
    PortfolioMandateBinding,
    RiskFreeSeries,
)
from sqlalchemy import and_, func, or_, select, tuple_
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


def _latest_reference_evidence_timestamp(rows: list[Any]) -> datetime | None:
    timestamps: list[datetime] = []
    for row in rows:
        for field_name in ("observed_at", "source_timestamp", "updated_at", "created_at"):
            value = getattr(row, field_name, None)
            if isinstance(value, datetime):
                timestamps.append(value)
    return max(timestamps) if timestamps else None


def _latest_effective_rows(rows: list[Any], *key_fields: str) -> list[Any]:
    latest_by_key: dict[tuple[Any, ...], Any] = {}
    for row in sorted(
        rows,
        key=lambda item: (
            tuple(getattr(item, field) for field in key_fields),
            getattr(item, "effective_from", None)
            or getattr(item, "composition_effective_from", None)
            or date.min,
            getattr(item, "updated_at", None) or datetime.min,
            getattr(item, "created_at", None) or datetime.min,
        ),
        reverse=True,
    ):
        key = tuple(getattr(row, field) for field in key_fields)
        latest_by_key.setdefault(key, row)
    return sorted(
        latest_by_key.values(),
        key=lambda item: tuple(getattr(item, field) for field in key_fields),
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

    async def resolve_model_portfolio_definition(
        self,
        model_portfolio_id: str,
        as_of_date: date,
    ):
        stmt = (
            select(ModelPortfolioDefinition)
            .where(
                ModelPortfolioDefinition.model_portfolio_id == model_portfolio_id,
                ModelPortfolioDefinition.approval_status == "approved",
                _effective_filter(
                    ModelPortfolioDefinition.effective_from,
                    ModelPortfolioDefinition.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                ModelPortfolioDefinition.effective_from.desc(),
                ModelPortfolioDefinition.approved_at.desc().nulls_last(),
                ModelPortfolioDefinition.updated_at.desc(),
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_model_portfolio_targets(
        self,
        model_portfolio_id: str,
        model_portfolio_version: str,
        as_of_date: date,
        *,
        include_inactive_targets: bool = False,
    ) -> list[ModelPortfolioTarget]:
        stmt = (
            select(ModelPortfolioTarget)
            .where(
                ModelPortfolioTarget.model_portfolio_id == model_portfolio_id,
                ModelPortfolioTarget.model_portfolio_version == model_portfolio_version,
                _effective_filter(
                    ModelPortfolioTarget.effective_from,
                    ModelPortfolioTarget.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                ModelPortfolioTarget.instrument_id.asc(),
                ModelPortfolioTarget.effective_from.desc(),
            )
        )
        if not include_inactive_targets:
            stmt = stmt.where(ModelPortfolioTarget.target_status == "active")
        result = await self._db.execute(stmt)
        rows = list(result.scalars().all())
        return _latest_effective_rows(
            rows,
            "model_portfolio_id",
            "model_portfolio_version",
            "instrument_id",
        )

    async def resolve_discretionary_mandate_binding(
        self,
        portfolio_id: str,
        as_of_date: date,
        *,
        mandate_id: str | None = None,
        booking_center_code: str | None = None,
    ):
        stmt = (
            select(PortfolioMandateBinding)
            .where(
                PortfolioMandateBinding.portfolio_id == portfolio_id,
                PortfolioMandateBinding.mandate_type == "discretionary",
                _effective_filter(
                    PortfolioMandateBinding.effective_from,
                    PortfolioMandateBinding.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                PortfolioMandateBinding.effective_from.desc(),
                PortfolioMandateBinding.observed_at.desc().nulls_last(),
                PortfolioMandateBinding.binding_version.desc(),
                PortfolioMandateBinding.updated_at.desc(),
            )
            .limit(1)
        )
        if mandate_id:
            stmt = stmt.where(PortfolioMandateBinding.mandate_id == mandate_id)
        if booking_center_code:
            stmt = stmt.where(PortfolioMandateBinding.booking_center_code == booking_center_code)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_instrument_eligibility_profiles(
        self,
        security_ids: list[str],
        as_of_date: date,
    ) -> list[InstrumentEligibilityProfile]:
        if not security_ids:
            return []
        stmt = (
            select(InstrumentEligibilityProfile)
            .where(
                InstrumentEligibilityProfile.security_id.in_(security_ids),
                _effective_filter(
                    InstrumentEligibilityProfile.effective_from,
                    InstrumentEligibilityProfile.effective_to,
                    as_of_date,
                ),
            )
            .order_by(
                InstrumentEligibilityProfile.security_id.asc(),
                InstrumentEligibilityProfile.effective_from.desc(),
                InstrumentEligibilityProfile.observed_at.desc().nulls_last(),
                InstrumentEligibilityProfile.eligibility_version.desc(),
                InstrumentEligibilityProfile.updated_at.desc(),
            )
        )
        result = await self._db.execute(stmt)
        return _latest_effective_rows(list(result.scalars().all()), "security_id")

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
        result = await self._db.execute(
            stmt.order_by(
                BenchmarkDefinition.benchmark_id.asc(),
                BenchmarkDefinition.effective_from.desc(),
            )
        )
        return _latest_effective_rows(list(result.scalars().all()), "benchmark_id")

    async def list_index_definitions(
        self,
        as_of_date: date,
        index_ids: list[str] | None = None,
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
        if index_ids:
            stmt = stmt.where(IndexDefinition.index_id.in_(index_ids))
        if index_currency:
            stmt = stmt.where(IndexDefinition.index_currency == index_currency.upper())
        if index_type:
            stmt = stmt.where(IndexDefinition.index_type == index_type)
        if index_status:
            stmt = stmt.where(IndexDefinition.index_status == index_status)
        result = await self._db.execute(
            stmt.order_by(IndexDefinition.index_id.asc(), IndexDefinition.effective_from.desc())
        )
        return _latest_effective_rows(list(result.scalars().all()), "index_id")

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
        return _latest_effective_rows(
            list(result.scalars().all()),
            "benchmark_id",
            "index_id",
        )

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
        rows = _latest_effective_rows(rows, "benchmark_id", "index_id")
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
        return self._canonicalize_risk_free_series_rows(list(result.scalars().all()))

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
            "latest_evidence_timestamp": _latest_reference_evidence_timestamp(
                price_points + benchmark_returns
            ),
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
            "observed_dates": all_dates,
            "latest_evidence_timestamp": _latest_reference_evidence_timestamp(points),
        }

    @staticmethod
    def _canonicalize_risk_free_series_rows(rows: list[RiskFreeSeries]) -> list[RiskFreeSeries]:
        if not rows:
            return []

        def sort_key(row: RiskFreeSeries) -> tuple[date, int, str, str, str]:
            quality_status = getattr(row, "quality_status", "") or ""
            source_timestamp = getattr(row, "source_timestamp", None)
            return (
                row.series_date,
                0 if quality_status.lower() == "accepted" else 1,
                source_timestamp.isoformat() if source_timestamp else "",
                getattr(row, "risk_free_curve_id", "") or "",
                getattr(row, "series_id", "") or "",
            )

        selected_by_date: dict[date, RiskFreeSeries] = {}
        for row in sorted(rows, key=sort_key):
            selected_by_date[row.series_date] = row
        return [selected_by_date[current_date] for current_date in sorted(selected_by_date)]

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

    async def list_latest_market_prices(
        self,
        *,
        security_ids: list[str],
        as_of_date: date,
    ) -> list[MarketPrice]:
        if not security_ids:
            return []

        latest_price_dates = (
            select(
                MarketPrice.security_id,
                func.max(MarketPrice.price_date).label("latest_price_date"),
            )
            .where(
                MarketPrice.security_id.in_(security_ids),
                MarketPrice.price_date <= as_of_date,
            )
            .group_by(MarketPrice.security_id)
            .subquery()
        )
        stmt = (
            select(MarketPrice)
            .join(
                latest_price_dates,
                and_(
                    MarketPrice.security_id == latest_price_dates.c.security_id,
                    MarketPrice.price_date == latest_price_dates.c.latest_price_date,
                ),
            )
            .order_by(MarketPrice.security_id.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_latest_fx_rates(
        self,
        *,
        currency_pairs: list[tuple[str, str]],
        as_of_date: date,
    ) -> list[FxRate]:
        if not currency_pairs:
            return []

        normalized_pairs = [(base.upper(), quote.upper()) for base, quote in currency_pairs]
        latest_rate_dates = (
            select(
                FxRate.from_currency,
                FxRate.to_currency,
                func.max(FxRate.rate_date).label("latest_rate_date"),
            )
            .where(
                tuple_(FxRate.from_currency, FxRate.to_currency).in_(normalized_pairs),
                FxRate.rate_date <= as_of_date,
            )
            .group_by(FxRate.from_currency, FxRate.to_currency)
            .subquery()
        )
        stmt = (
            select(FxRate)
            .join(
                latest_rate_dates,
                and_(
                    FxRate.from_currency == latest_rate_dates.c.from_currency,
                    FxRate.to_currency == latest_rate_dates.c.to_currency,
                    FxRate.rate_date == latest_rate_dates.c.latest_rate_date,
                ),
            )
            .order_by(FxRate.from_currency.asc(), FxRate.to_currency.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
