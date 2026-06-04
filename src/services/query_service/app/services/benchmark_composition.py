from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..dtos.reference_integration_dto import (
    BenchmarkCompositionWindowRequest,
    BenchmarkCompositionWindowResponse,
    IntegrationWindow,
)
from .integration_value_normalization import as_decimal
from .reference_data_helpers import (
    latest_effective_records,
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
    resolve_component_window_rows,
)
from .source_data_runtime import source_product_runtime_metadata


@dataclass(frozen=True)
class BenchmarkCompositionDefinitionContext:
    benchmark_currency: str
    definitions: list[Any]


def benchmark_composition_definition_context(
    definition_rows: list[Any],
) -> BenchmarkCompositionDefinitionContext | None:
    if not definition_rows:
        return None

    benchmark_currencies = {row.benchmark_currency for row in definition_rows}
    if len(benchmark_currencies) != 1:
        raise ValueError(
            "Benchmark definition currency changed within requested composition window."
        )

    return BenchmarkCompositionDefinitionContext(
        benchmark_currency=next(iter(benchmark_currencies)),
        definitions=latest_effective_records(
            definition_rows,
            key_fields=("benchmark_id",),
            effective_from_field="effective_from",
        ),
    )


async def resolve_benchmark_composition_window_response(
    *,
    repository: Any,
    benchmark_id: str,
    request: BenchmarkCompositionWindowRequest,
) -> BenchmarkCompositionWindowResponse | None:
    definition_rows = await repository.list_benchmark_definitions_overlapping_window(
        benchmark_id=benchmark_id,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    definition_context = benchmark_composition_definition_context(definition_rows)
    if definition_context is None:
        return None

    component_rows = await repository.list_benchmark_components_overlapping_window(
        benchmark_id=benchmark_id,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    return build_benchmark_composition_window_response(
        benchmark_id=benchmark_id,
        request=request,
        definition_context=definition_context,
        component_rows=component_rows,
    )


def build_benchmark_composition_window_response(
    *,
    benchmark_id: str,
    request: BenchmarkCompositionWindowRequest,
    definition_context: BenchmarkCompositionDefinitionContext,
    component_rows: list[Any],
) -> BenchmarkCompositionWindowResponse:
    components = resolve_component_window_rows(
        component_rows,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    evidence_rows = definition_context.definitions + components

    return BenchmarkCompositionWindowResponse(
        benchmark_id=benchmark_id,
        benchmark_currency=definition_context.benchmark_currency,
        resolved_window=IntegrationWindow(
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        segments=[
            {
                "index_id": component.index_id,
                "composition_weight": as_decimal(component.composition_weight),
                "composition_effective_from": component.composition_effective_from,
                "composition_effective_to": component.composition_effective_to,
                "rebalance_event_id": component.rebalance_event_id,
            }
            for component in components
        ],
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-service",
            "generated_by": "integration.benchmark_composition_window",
        },
        **source_product_runtime_metadata(
            request.window.end_date,
            data_quality_status=market_reference_data_quality_status(
                evidence_rows,
                required_count=len(evidence_rows),
            ),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(evidence_rows),
        ),
    )
