from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.market_reference_quality import quality_status_summary_key

from ..dtos.reference_integration_dto import (
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
    IntegrationWindow,
    ReferencePageMetadata,
)
from .integration_value_normalization import as_decimal
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
    resolve_component_window_rows,
)
from .reference_data_mappers import (
    benchmark_component_series_response,
    benchmark_market_series_point,
)
from .request_fingerprint import request_fingerprint as build_request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


@dataclass(frozen=True)
class BenchmarkMarketSeriesFxContext:
    source_currency: str | None
    target_currency: str | None
    should_read_fx_rates: bool
    initial_normalization_status: str


@dataclass(frozen=True)
class BenchmarkMarketSeriesRequestScope:
    request_fingerprint: str
    requested_fields: set[str]
    page_size: int
    cursor_index_id: str | None


def benchmark_market_series_request_scope(
    *,
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    cursor: dict[str, Any],
) -> BenchmarkMarketSeriesRequestScope:
    request_fingerprint = build_request_fingerprint(
        {
            "benchmark_id": benchmark_id,
            "as_of_date": request.as_of_date.isoformat(),
            "window": {
                "start_date": request.window.start_date.isoformat(),
                "end_date": request.window.end_date.isoformat(),
            },
            "frequency": request.frequency,
            "target_currency": request.target_currency,
            "series_fields": sorted(request.series_fields),
        }
    )
    token_scope = cursor.get("scope_fingerprint")
    if token_scope and token_scope != request_fingerprint:
        raise ValueError("Benchmark market series page token does not match request scope.")

    page = getattr(request, "page", None)
    return BenchmarkMarketSeriesRequestScope(
        request_fingerprint=request_fingerprint,
        requested_fields=set(request.series_fields),
        page_size=getattr(page, "page_size", 250),
        cursor_index_id=cursor.get("last_index_id"),
    )


def benchmark_market_series_next_page_token_payload(
    *,
    request_scope: BenchmarkMarketSeriesRequestScope,
    has_more: bool,
    index_ids: list[str],
) -> dict[str, str] | None:
    if not has_more or not index_ids:
        return None
    return {
        "scope_fingerprint": request_scope.request_fingerprint,
        "last_index_id": index_ids[-1],
    }


def benchmark_market_series_fx_context(
    *,
    benchmark_currency: str,
    target_currency: str | None,
    requested_fields: set[str],
) -> BenchmarkMarketSeriesFxContext:
    if target_currency is None:
        return BenchmarkMarketSeriesFxContext(
            source_currency=None,
            target_currency=None,
            should_read_fx_rates=False,
            initial_normalization_status="native_component_series_only",
        )

    if benchmark_currency != target_currency and "fx_rate" in requested_fields:
        return BenchmarkMarketSeriesFxContext(
            source_currency=benchmark_currency,
            target_currency=target_currency,
            should_read_fx_rates=True,
            initial_normalization_status="native_component_series_only",
        )

    normalization_status = (
        "native_component_series_with_identity_benchmark_to_target_fx_context"
        if benchmark_currency == target_currency
        else "native_component_series_without_fx_context_request"
    )

    return BenchmarkMarketSeriesFxContext(
        source_currency=benchmark_currency,
        target_currency=target_currency,
        should_read_fx_rates=False,
        initial_normalization_status=normalization_status,
    )


def benchmark_market_series_normalization_status(
    fx_context: BenchmarkMarketSeriesFxContext,
    fx_rates: dict[date, Decimal],
) -> str:
    if not fx_context.should_read_fx_rates:
        return fx_context.initial_normalization_status
    if fx_rates:
        return "native_component_series_with_benchmark_to_target_fx_context"
    return "native_component_series_with_missing_benchmark_to_target_fx_context"


def build_benchmark_market_series_response(
    *,
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    benchmark_currency: str,
    request_scope_fingerprint: str,
    page_size: int,
    has_more: bool,
    next_page_token: str | None,
    index_ids: list[str],
    component_rows: list[Any],
    index_prices: list[Any],
    index_returns: list[Any],
    benchmark_returns: list[Any],
    fx_rates: dict[date, Decimal],
    fx_context: BenchmarkMarketSeriesFxContext,
) -> BenchmarkMarketSeriesResponse:
    requested_fields = set(request.series_fields)
    components = resolve_component_window_rows(
        component_rows,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )

    prices_by_index_date = {(row.index_id, row.series_date): row for row in index_prices}
    returns_by_index_date = {(row.index_id, row.series_date): row for row in index_returns}
    benchmark_return_by_date = {row.series_date: row for row in benchmark_returns}
    component_segments_by_index: dict[str, list[Any]] = {}
    for row in components:
        component_segments_by_index.setdefault(row.index_id, []).append(row)

    all_dates = sorted(
        {row.series_date for row in index_prices + index_returns + benchmark_returns}
        | set(fx_rates.keys())
    )
    component_series_all = []
    for index_id in sorted(index_ids):
        points = []
        for current_date in all_dates:
            price_row = prices_by_index_date.get((index_id, current_date))
            return_row = returns_by_index_date.get((index_id, current_date))
            benchmark_return_row = benchmark_return_by_date.get(current_date)
            component_weight = None
            for segment in component_segments_by_index.get(index_id, []):
                if segment.composition_effective_from <= current_date and (
                    segment.composition_effective_to is None
                    or segment.composition_effective_to >= current_date
                ):
                    component_weight = as_decimal(segment.composition_weight)
                    break
            points.append(
                benchmark_market_series_point(
                    series_date=current_date,
                    requested_fields=requested_fields,
                    price_row=price_row,
                    return_row=return_row,
                    benchmark_return_row=benchmark_return_row,
                    component_weight=component_weight,
                    fx_rate=fx_rates.get(current_date),
                )
            )
        component_series_all.append(
            benchmark_component_series_response(index_id=index_id, points=points)
        )

    component_series = component_series_all[:page_size]
    returned_index_ids = {series.index_id for series in component_series}
    returned_index_prices = [row for row in index_prices if row.index_id in returned_index_ids]
    returned_index_returns = [row for row in index_returns if row.index_id in returned_index_ids]
    returned_components = [row for row in components if row.index_id in returned_index_ids]
    returned_evidence_rows = (
        returned_components + returned_index_prices + returned_index_returns + benchmark_returns
    )
    required_evidence_count = (
        len(returned_evidence_rows) + 1 if has_more else len(returned_evidence_rows)
    )

    quality_status_summary: dict[str, int] = {}
    for component in component_series:
        for point in component.points:
            if point.quality_status:
                summary_key = quality_status_summary_key(point.quality_status)
                quality_status_summary[summary_key] = quality_status_summary.get(summary_key, 0) + 1

    return BenchmarkMarketSeriesResponse(
        benchmark_id=benchmark_id,
        as_of_date=request.as_of_date,
        benchmark_currency=benchmark_currency,
        target_currency=request.target_currency,
        resolved_window=IntegrationWindow(
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        frequency=request.frequency,
        component_series=component_series,
        quality_status_summary=quality_status_summary,
        fx_context_source_currency=fx_context.source_currency,
        fx_context_target_currency=fx_context.target_currency,
        normalization_policy="native_component_series_downstream_normalization_required",
        normalization_status=benchmark_market_series_normalization_status(
            fx_context,
            fx_rates,
        ),
        component_metadata_policy="targeted_index_catalog_lookup_required_for_component_metadata",
        request_fingerprint=request_scope_fingerprint,
        page=ReferencePageMetadata(
            page_size=page_size,
            sort_key="index_id:asc",
            returned_component_count=len(component_series),
            request_scope_fingerprint=request_scope_fingerprint,
            next_page_token=next_page_token,
        ),
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-service",
            "generated_by": "integration.market_series",
        },
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status=market_reference_data_quality_status(
                returned_evidence_rows,
                required_count=required_evidence_count,
            ),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(returned_evidence_rows),
        ),
    )
