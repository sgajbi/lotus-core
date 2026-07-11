from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from ..dtos.reference_integration_dto import (
    BenchmarkComponentResponse,
    BenchmarkDefinitionResponse,
    BenchmarkReturnSeriesPoint,
    ClassificationTaxonomyEntry,
    ComponentSeriesResponse,
    IndexDefinitionResponse,
    IndexPriceSeriesPoint,
    IndexReturnSeriesPoint,
    RiskFreeSeriesPoint,
    SeriesPoint,
)
from .integration_value_normalization import (
    as_decimal,
)


def benchmark_component_response(row: Any) -> BenchmarkComponentResponse:
    return BenchmarkComponentResponse(
        index_id=row.index_id,
        composition_weight=as_decimal(row.composition_weight),
        composition_effective_from=row.composition_effective_from,
        composition_effective_to=row.composition_effective_to,
        rebalance_event_id=row.rebalance_event_id,
    )


def benchmark_definition_response(
    row: Any,
    *,
    components: list[Any] | None = None,
) -> BenchmarkDefinitionResponse:
    return BenchmarkDefinitionResponse(
        benchmark_id=row.benchmark_id,
        benchmark_name=row.benchmark_name,
        benchmark_type=row.benchmark_type,
        benchmark_currency=row.benchmark_currency,
        return_convention=row.return_convention,
        benchmark_status=row.benchmark_status,
        benchmark_family=row.benchmark_family,
        benchmark_provider=row.benchmark_provider,
        rebalance_frequency=row.rebalance_frequency,
        classification_set_id=row.classification_set_id,
        classification_labels=dict(row.classification_labels or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        components=[benchmark_component_response(component) for component in components or []],
    )


def index_definition_response(row: Any) -> IndexDefinitionResponse:
    return IndexDefinitionResponse(
        index_id=row.index_id,
        index_name=row.index_name,
        index_currency=row.index_currency,
        index_type=row.index_type,
        index_status=row.index_status,
        index_provider=row.index_provider,
        index_market=row.index_market,
        classification_set_id=row.classification_set_id,
        classification_labels=dict(row.classification_labels or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
    )


def index_price_series_point(row: Any) -> IndexPriceSeriesPoint:
    return IndexPriceSeriesPoint(
        series_date=row.series_date,
        index_price=as_decimal(row.index_price),
        series_currency=row.series_currency,
        value_convention=row.value_convention,
        quality_status=row.quality_status,
    )


def index_return_series_point(row: Any) -> IndexReturnSeriesPoint:
    return IndexReturnSeriesPoint(
        series_date=row.series_date,
        index_return=as_decimal(row.index_return),
        return_period=row.return_period,
        return_convention=row.return_convention,
        series_currency=row.series_currency,
        quality_status=row.quality_status,
    )


def benchmark_return_series_point(row: Any) -> BenchmarkReturnSeriesPoint:
    return BenchmarkReturnSeriesPoint(
        series_date=row.series_date,
        benchmark_return=as_decimal(row.benchmark_return),
        return_period=row.return_period,
        return_convention=row.return_convention,
        series_currency=row.series_currency,
        quality_status=row.quality_status,
    )


def benchmark_market_series_point(
    *,
    series_date: Any,
    requested_fields: set[str],
    price_row: Any | None,
    return_row: Any | None,
    benchmark_return_row: Any | None,
    component_weight: Decimal | None,
    fx_rate: Decimal | None,
) -> SeriesPoint:
    return SeriesPoint(
        series_date=series_date,
        series_currency=_first_market_series_value(
            "series_currency",
            price_row,
            return_row,
            benchmark_return_row,
        ),
        index_price=_requested_row_decimal(
            requested_fields,
            "index_price",
            price_row,
            "index_price",
        ),
        index_return=_requested_row_decimal(
            requested_fields,
            "index_return",
            return_row,
            "index_return",
        ),
        benchmark_return=_requested_row_decimal(
            requested_fields,
            "benchmark_return",
            benchmark_return_row,
            "benchmark_return",
        ),
        component_weight=_requested_value(requested_fields, "component_weight", component_weight),
        fx_rate=_requested_value(requested_fields, "fx_rate", fx_rate),
        quality_status=_first_market_series_value(
            "quality_status",
            price_row,
            return_row,
            benchmark_return_row,
        ),
    )


def _first_market_series_value(field_name: str, *rows: Any | None) -> Any | None:
    for row in rows:
        if row is not None and (value := getattr(row, field_name, None)):
            return value
    return None


def _requested_row_decimal(
    requested_fields: set[str],
    response_field: str,
    row: Any | None,
    row_field: str,
) -> Decimal | None:
    if row is None or response_field not in requested_fields:
        return None
    return cast(Decimal, as_decimal(getattr(row, row_field)))


def _requested_value(
    requested_fields: set[str],
    response_field: str,
    value: Decimal | None,
) -> Decimal | None:
    return value if response_field in requested_fields else None


def benchmark_component_series_response(
    *,
    index_id: str,
    points: list[SeriesPoint],
) -> ComponentSeriesResponse:
    return ComponentSeriesResponse(index_id=index_id, points=points)


def risk_free_series_point(row: Any) -> RiskFreeSeriesPoint:
    return RiskFreeSeriesPoint(
        series_date=row.series_date,
        value=as_decimal(row.value),
        value_convention=row.value_convention,
        day_count_convention=row.day_count_convention,
        compounding_convention=row.compounding_convention,
        series_currency=row.series_currency,
        quality_status=row.quality_status,
    )


def classification_taxonomy_entry(row: Any) -> ClassificationTaxonomyEntry:
    return ClassificationTaxonomyEntry(
        classification_set_id=row.classification_set_id,
        taxonomy_scope=row.taxonomy_scope,
        dimension_name=row.dimension_name,
        dimension_value=row.dimension_value,
        dimension_description=row.dimension_description,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
    )
