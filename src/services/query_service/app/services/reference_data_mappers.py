from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from ..dtos.reference_integration_dto import (
    ClassificationTaxonomyEntry,
    ComponentSeriesResponse,
    SeriesPoint,
)
from .integration_value_normalization import (
    as_decimal,
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
