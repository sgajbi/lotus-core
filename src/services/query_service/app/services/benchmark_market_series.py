from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

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


@dataclass(frozen=True)
class BenchmarkMarketSeriesEvidencePlan:
    include_index_prices: bool
    include_index_returns: bool
    include_benchmark_returns: bool
    include_fx_rates: bool


@dataclass(frozen=True)
class BenchmarkMarketSeriesIndexPage:
    index_ids: list[str]
    has_more: bool


@dataclass(frozen=True)
class BenchmarkMarketSeriesRows:
    components: list[Any]
    prices_by_index_date: dict[tuple[str, date], Any]
    returns_by_index_date: dict[tuple[str, date], Any]
    benchmark_return_by_date: dict[date, Any]
    component_segments_by_index: dict[str, list[Any]]
    all_dates: list[date]


def benchmark_market_series_currency(
    *,
    definition: Any | None,
    target_currency: str | None,
) -> str:
    if definition is not None:
        return cast(str, definition.benchmark_currency)
    return target_currency or "UNKNOWN"


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


def benchmark_market_series_index_page(
    *,
    candidate_index_ids: list[str],
    page_size: int,
) -> BenchmarkMarketSeriesIndexPage:
    return BenchmarkMarketSeriesIndexPage(
        index_ids=candidate_index_ids[:page_size],
        has_more=len(candidate_index_ids) > page_size,
    )


def benchmark_market_series_page_token(
    *,
    request_scope: BenchmarkMarketSeriesRequestScope,
    has_more: bool,
    index_ids: list[str],
    encode_page_token: Callable[[dict[str, str]], str],
) -> str | None:
    payload = benchmark_market_series_next_page_token_payload(
        request_scope=request_scope,
        has_more=has_more,
        index_ids=index_ids,
    )
    if payload is None:
        return None
    return encode_page_token(payload)


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


def benchmark_market_series_evidence_plan(
    *,
    requested_fields: set[str],
    fx_context: BenchmarkMarketSeriesFxContext,
) -> BenchmarkMarketSeriesEvidencePlan:
    return BenchmarkMarketSeriesEvidencePlan(
        include_index_prices="index_price" in requested_fields,
        include_index_returns="index_return" in requested_fields,
        include_benchmark_returns="benchmark_return" in requested_fields,
        include_fx_rates=fx_context.should_read_fx_rates,
    )


def benchmark_market_series_evidence_read_names(
    evidence_plan: BenchmarkMarketSeriesEvidencePlan,
) -> list[str]:
    read_names = ["components"]
    if evidence_plan.include_index_prices:
        read_names.append("index_prices")
    if evidence_plan.include_index_returns:
        read_names.append("index_returns")
    if evidence_plan.include_benchmark_returns:
        read_names.append("benchmark_returns")
    if evidence_plan.include_fx_rates:
        read_names.append("fx_rates")
    return read_names


def benchmark_market_series_evidence_read_factories(
    *,
    repository: Any,
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    benchmark_currency: str,
    index_ids: list[str],
) -> Mapping[str, Callable[[], Awaitable[Any]]]:
    return {
        "components": lambda: repository.list_benchmark_components_overlapping_window(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
            index_ids=index_ids,
        ),
        "index_prices": lambda: repository.list_index_price_points(
            index_ids=index_ids,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        "index_returns": lambda: repository.list_index_return_points(
            index_ids=index_ids,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        "benchmark_returns": lambda: repository.list_benchmark_return_points(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        "fx_rates": lambda: repository.get_fx_rates(
            from_currency=benchmark_currency,
            to_currency=request.target_currency,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
    }


async def benchmark_market_series_read_evidence(
    *,
    evidence_plan: BenchmarkMarketSeriesEvidencePlan,
    read_factories: Mapping[str, Callable[[], Awaitable[Any]]],
) -> dict[str, Any]:
    market_results = {}
    for read_name in benchmark_market_series_evidence_read_names(evidence_plan):
        market_results[read_name] = await read_factories[read_name]()
    return market_results


async def resolve_benchmark_market_series_response(
    *,
    repository: Any,
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    decode_page_token: Callable[[str | None], dict[str, Any]],
    encode_page_token: Callable[[dict[str, str]], str],
) -> BenchmarkMarketSeriesResponse:
    definition = await repository.get_benchmark_definition(
        benchmark_id,
        request.as_of_date,
    )
    benchmark_currency = benchmark_market_series_currency(
        definition=definition,
        target_currency=request.target_currency,
    )
    page = getattr(request, "page", None)
    page_token = getattr(page, "page_token", None)
    request_scope = benchmark_market_series_request_scope(
        benchmark_id=benchmark_id,
        request=request,
        cursor=decode_page_token(page_token),
    )
    candidate_index_ids = await repository.list_benchmark_component_index_ids_overlapping_window(
        benchmark_id=benchmark_id,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
        after_index_id=request_scope.cursor_index_id,
        limit=request_scope.page_size + 1,
    )
    index_page = benchmark_market_series_index_page(
        candidate_index_ids=candidate_index_ids,
        page_size=request_scope.page_size,
    )
    fx_context = benchmark_market_series_fx_context(
        benchmark_currency=benchmark_currency,
        target_currency=request.target_currency,
        requested_fields=request_scope.requested_fields,
    )
    evidence_plan = benchmark_market_series_evidence_plan(
        requested_fields=request_scope.requested_fields,
        fx_context=fx_context,
    )
    market_results = await benchmark_market_series_read_evidence(
        evidence_plan=evidence_plan,
        read_factories=benchmark_market_series_evidence_read_factories(
            repository=repository,
            benchmark_id=benchmark_id,
            request=request,
            benchmark_currency=benchmark_currency,
            index_ids=index_page.index_ids,
        ),
    )
    next_page_token = benchmark_market_series_page_token(
        request_scope=request_scope,
        has_more=index_page.has_more,
        index_ids=index_page.index_ids,
        encode_page_token=encode_page_token,
    )

    return build_benchmark_market_series_response(
        benchmark_id=benchmark_id,
        request=request,
        benchmark_currency=benchmark_currency,
        request_scope_fingerprint=request_scope.request_fingerprint,
        page_size=request_scope.page_size,
        has_more=index_page.has_more,
        next_page_token=next_page_token,
        index_ids=index_page.index_ids,
        component_rows=market_results["components"],
        index_prices=market_results.get("index_prices", []),
        index_returns=market_results.get("index_returns", []),
        benchmark_returns=market_results.get("benchmark_returns", []),
        fx_rates=market_results.get("fx_rates", {}),
        fx_context=fx_context,
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


def _benchmark_market_series_rows(
    *,
    component_rows: list[Any],
    index_prices: list[Any],
    index_returns: list[Any],
    benchmark_returns: list[Any],
    fx_rates: dict[date, Decimal],
    window: IntegrationWindow,
) -> BenchmarkMarketSeriesRows:
    components = resolve_component_window_rows(
        component_rows,
        start_date=window.start_date,
        end_date=window.end_date,
    )
    return BenchmarkMarketSeriesRows(
        components=components,
        prices_by_index_date=_rows_by_index_date(index_prices),
        returns_by_index_date=_rows_by_index_date(index_returns),
        benchmark_return_by_date=_rows_by_series_date(benchmark_returns),
        component_segments_by_index=_component_segments_by_index(components),
        all_dates=_market_series_dates(
            index_prices=index_prices,
            index_returns=index_returns,
            benchmark_returns=benchmark_returns,
            fx_rates=fx_rates,
        ),
    )


def _rows_by_index_date(rows: list[Any]) -> dict[tuple[str, date], Any]:
    return {(row.index_id, row.series_date): row for row in rows}


def _rows_by_series_date(rows: list[Any]) -> dict[date, Any]:
    return {row.series_date: row for row in rows}


def _component_segments_by_index(components: list[Any]) -> dict[str, list[Any]]:
    component_segments_by_index: dict[str, list[Any]] = {}
    for row in components:
        component_segments_by_index.setdefault(row.index_id, []).append(row)
    return component_segments_by_index


def _market_series_dates(
    *,
    index_prices: list[Any],
    index_returns: list[Any],
    benchmark_returns: list[Any],
    fx_rates: dict[date, Decimal],
) -> list[date]:
    return sorted(
        {row.series_date for row in index_prices + index_returns + benchmark_returns}
        | set(fx_rates.keys())
    )


def _component_weight_for_date(
    *,
    segments: list[Any],
    current_date: date,
) -> Decimal | None:
    for segment in segments:
        if segment.composition_effective_from <= current_date and (
            segment.composition_effective_to is None
            or segment.composition_effective_to >= current_date
        ):
            return cast(Decimal, as_decimal(segment.composition_weight))
    return None


def _benchmark_market_series_points(
    *,
    index_id: str,
    market_rows: BenchmarkMarketSeriesRows,
    requested_fields: set[str],
    fx_rates: dict[date, Decimal],
) -> list[Any]:
    points = []
    component_segments = market_rows.component_segments_by_index.get(index_id, [])
    for current_date in market_rows.all_dates:
        points.append(
            benchmark_market_series_point(
                series_date=current_date,
                requested_fields=requested_fields,
                price_row=market_rows.prices_by_index_date.get((index_id, current_date)),
                return_row=market_rows.returns_by_index_date.get((index_id, current_date)),
                benchmark_return_row=market_rows.benchmark_return_by_date.get(current_date),
                component_weight=_component_weight_for_date(
                    segments=component_segments,
                    current_date=current_date,
                ),
                fx_rate=fx_rates.get(current_date),
            )
        )
    return points


def _benchmark_component_series(
    *,
    index_ids: list[str],
    requested_fields: set[str],
    market_rows: BenchmarkMarketSeriesRows,
    fx_rates: dict[date, Decimal],
    page_size: int,
) -> list[Any]:
    component_series_all = [
        benchmark_component_series_response(
            index_id=index_id,
            points=_benchmark_market_series_points(
                index_id=index_id,
                market_rows=market_rows,
                requested_fields=requested_fields,
                fx_rates=fx_rates,
            ),
        )
        for index_id in sorted(index_ids)
    ]
    return component_series_all[:page_size]


def _returned_evidence_rows(
    *,
    component_series: list[Any],
    market_rows: BenchmarkMarketSeriesRows,
    index_prices: list[Any],
    index_returns: list[Any],
    benchmark_returns: list[Any],
) -> list[Any]:
    returned_index_ids = _returned_index_ids(component_series)
    returned_index_prices = _rows_for_index_ids(index_prices, returned_index_ids)
    returned_index_returns = _rows_for_index_ids(index_returns, returned_index_ids)
    returned_components = _rows_for_index_ids(market_rows.components, returned_index_ids)
    return returned_components + returned_index_prices + returned_index_returns + benchmark_returns


def _returned_index_ids(component_series: list[Any]) -> set[str]:
    return {series.index_id for series in component_series}


def _rows_for_index_ids(rows: list[Any], index_ids: set[str]) -> list[Any]:
    return [row for row in rows if row.index_id in index_ids]


def _required_evidence_count(
    *,
    returned_evidence_rows: list[Any],
    has_more: bool,
) -> int:
    if has_more:
        return len(returned_evidence_rows) + 1
    return len(returned_evidence_rows)


def _quality_status_summary(component_series: list[Any]) -> dict[str, int]:
    quality_status_summary: dict[str, int] = {}
    for component in component_series:
        for point in component.points:
            if point.quality_status:
                summary_key = quality_status_summary_key(point.quality_status)
                quality_status_summary[summary_key] = quality_status_summary.get(summary_key, 0) + 1
    return quality_status_summary


def _benchmark_market_series_page_metadata(
    *,
    page_size: int,
    component_series: list[Any],
    request_scope_fingerprint: str,
    next_page_token: str | None,
) -> ReferencePageMetadata:
    return ReferencePageMetadata(
        page_size=page_size,
        sort_key="index_id:asc",
        returned_component_count=len(component_series),
        request_scope_fingerprint=request_scope_fingerprint,
        next_page_token=next_page_token,
    )


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
    market_rows = _benchmark_market_series_rows(
        component_rows=component_rows,
        index_prices=index_prices,
        index_returns=index_returns,
        benchmark_returns=benchmark_returns,
        fx_rates=fx_rates,
        window=request.window,
    )
    component_series = _benchmark_component_series(
        index_ids=index_ids,
        requested_fields=requested_fields,
        market_rows=market_rows,
        fx_rates=fx_rates,
        page_size=page_size,
    )
    returned_evidence_rows = _returned_evidence_rows(
        component_series=component_series,
        market_rows=market_rows,
        index_prices=index_prices,
        index_returns=index_returns,
        benchmark_returns=benchmark_returns,
    )

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
        quality_status_summary=_quality_status_summary(component_series),
        fx_context_source_currency=fx_context.source_currency,
        fx_context_target_currency=fx_context.target_currency,
        normalization_policy="native_component_series_downstream_normalization_required",
        normalization_status=benchmark_market_series_normalization_status(
            fx_context,
            fx_rates,
        ),
        component_metadata_policy="targeted_index_catalog_lookup_required_for_component_metadata",
        request_fingerprint=request_scope_fingerprint,
        page=_benchmark_market_series_page_metadata(
            page_size=page_size,
            component_series=component_series,
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
                required_count=_required_evidence_count(
                    returned_evidence_rows=returned_evidence_rows,
                    has_more=has_more,
                ),
            ),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(returned_evidence_rows),
        ),
    )
