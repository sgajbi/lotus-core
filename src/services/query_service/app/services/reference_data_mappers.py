from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..dtos.reference_integration_dto import (
    BenchmarkComponentResponse,
    BenchmarkDefinitionResponse,
    IndexDefinitionResponse,
)


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def benchmark_component_response(row: Any) -> BenchmarkComponentResponse:
    return BenchmarkComponentResponse(
        index_id=row.index_id,
        composition_weight=_as_decimal(row.composition_weight),
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
