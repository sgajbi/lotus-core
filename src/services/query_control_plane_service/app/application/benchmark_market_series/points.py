"""Typed benchmark component point construction for market-series windows."""

from datetime import date
from decimal import Decimal

from portfolio_common.market_reference_quality import quality_status_summary_key

from ...contracts.benchmark_market_series import (
    BenchmarkMarketSeriesRequest,
    ComponentSeriesResponse,
    SeriesPoint,
)
from ...domain.benchmark_definition import BenchmarkComponentEvidence
from ...domain.benchmark_return_series import BenchmarkReturnEvidence
from ...domain.index_series import IndexPriceEvidence, IndexReturnEvidence
from ...domain.market_fx import FxRateEvidence
from .policy import BenchmarkMarketSeriesFxContext

IDENTITY_FX_RATE = Decimal("1.0000000000")


def build_component_series(
    *,
    index_ids: tuple[str, ...],
    request: BenchmarkMarketSeriesRequest,
    components: list[BenchmarkComponentEvidence],
    index_prices: list[IndexPriceEvidence],
    index_returns: list[IndexReturnEvidence],
    benchmark_returns: list[BenchmarkReturnEvidence],
    fx_rates: list[FxRateEvidence],
    fx_context: BenchmarkMarketSeriesFxContext,
) -> list[ComponentSeriesResponse]:
    """Build stable component point series from typed source evidence."""

    requested_fields = frozenset(request.series_fields)
    prices_by_key = {(row.index_id, row.series_date): row for row in index_prices}
    returns_by_key = {(row.index_id, row.series_date): row for row in index_returns}
    benchmark_returns_by_date = {row.series_date: row for row in benchmark_returns}
    fx_by_date = {row.rate_date: row.rate for row in fx_rates}
    segments_by_index: dict[str, list[BenchmarkComponentEvidence]] = {}
    for component in components:
        segments_by_index.setdefault(component.index_id, []).append(component)
    dates = _series_dates(
        request=request,
        components=components,
        index_prices=index_prices,
        index_returns=index_returns,
        benchmark_returns=benchmark_returns,
        fx_rates=fx_rates,
    )
    return [
        ComponentSeriesResponse(
            index_id=index_id,
            points=[
                _series_point(
                    series_date=series_date,
                    requested_fields=requested_fields,
                    segments=segments_by_index.get(index_id, []),
                    price=prices_by_key.get((index_id, series_date)),
                    index_return=returns_by_key.get((index_id, series_date)),
                    benchmark_return=benchmark_returns_by_date.get(series_date),
                    fx_rate=_fx_rate_for_date(
                        series_date=series_date,
                        requested_fields=requested_fields,
                        fx_context=fx_context,
                        fx_by_date=fx_by_date,
                    ),
                )
                for series_date in dates
            ],
        )
        for index_id in sorted(index_ids)
    ]


def normalization_status(
    *, fx_context: BenchmarkMarketSeriesFxContext, fx_rates: list[FxRateEvidence]
) -> str:
    """Describe optional benchmark-to-target FX evidence attached to native series."""

    if not fx_context.should_read_fx_rates:
        return fx_context.initial_normalization_status
    if fx_rates:
        return "native_component_series_with_benchmark_to_target_fx_context"
    return "native_component_series_with_missing_benchmark_to_target_fx_context"


def quality_status_summary(
    component_series: list[ComponentSeriesResponse],
) -> dict[str, int]:
    """Summarize returned point quality using canonical normalized keys."""

    summary: dict[str, int] = {}
    for component in component_series:
        for point in component.points:
            if point.quality_status is None:
                continue
            key = quality_status_summary_key(point.quality_status)
            summary[key] = summary.get(key, 0) + 1
    return dict(sorted(summary.items()))


def _series_dates(
    *,
    request: BenchmarkMarketSeriesRequest,
    components: list[BenchmarkComponentEvidence],
    index_prices: list[IndexPriceEvidence],
    index_returns: list[IndexReturnEvidence],
    benchmark_returns: list[BenchmarkReturnEvidence],
    fx_rates: list[FxRateEvidence],
) -> list[date]:
    dates = {row.series_date for row in index_prices}
    dates.update(row.series_date for row in index_returns)
    dates.update(row.series_date for row in benchmark_returns)
    dates.update(row.rate_date for row in fx_rates)
    if "component_weight" in request.series_fields:
        dates.update(
            max(request.window.start_date, row.composition_effective_from) for row in components
        )
    return sorted(dates)


def _series_point(
    *,
    series_date: date,
    requested_fields: frozenset[str],
    segments: list[BenchmarkComponentEvidence],
    price: IndexPriceEvidence | None,
    index_return: IndexReturnEvidence | None,
    benchmark_return: BenchmarkReturnEvidence | None,
    fx_rate: Decimal | None,
) -> SeriesPoint:
    component = _active_component(segments=segments, series_date=series_date)
    return SeriesPoint(
        series_date=series_date,
        series_currency=_first_text(
            price.series_currency if price else None,
            index_return.series_currency if index_return else None,
            benchmark_return.series_currency if benchmark_return else None,
        ),
        index_price=price.index_price if price and "index_price" in requested_fields else None,
        index_return=(
            index_return.index_return
            if index_return and "index_return" in requested_fields
            else None
        ),
        benchmark_return=(
            benchmark_return.benchmark_return
            if benchmark_return and "benchmark_return" in requested_fields
            else None
        ),
        component_weight=(
            component.composition_weight
            if component and "component_weight" in requested_fields
            else None
        ),
        fx_rate=fx_rate,
        quality_status=_first_text(
            price.quality_status if price else None,
            index_return.quality_status if index_return else None,
            benchmark_return.quality_status if benchmark_return else None,
            component.quality_status if component else None,
        ),
    )


def _active_component(
    *, segments: list[BenchmarkComponentEvidence], series_date: date
) -> BenchmarkComponentEvidence | None:
    return next(
        (
            segment
            for segment in segments
            if segment.composition_effective_from <= series_date
            and (
                segment.composition_effective_to is None
                or segment.composition_effective_to >= series_date
            )
        ),
        None,
    )


def _fx_rate_for_date(
    *,
    series_date: date,
    requested_fields: frozenset[str],
    fx_context: BenchmarkMarketSeriesFxContext,
    fx_by_date: dict[date, Decimal],
) -> Decimal | None:
    if "fx_rate" not in requested_fields:
        return None
    if (
        fx_context.source_currency is not None
        and fx_context.source_currency == fx_context.target_currency
    ):
        return IDENTITY_FX_RATE
    return fx_by_date.get(series_date)


def _first_text(*values: str | None) -> str | None:
    return next((value for value in values if value), None)
