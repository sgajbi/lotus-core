"""Application use case for effective benchmark definition evidence."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.benchmark_definition import (
    BenchmarkComponentResponse,
    BenchmarkDefinitionRequest,
    BenchmarkDefinitionResponse,
)
from ..domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)
from ..ports.benchmark_definition import BenchmarkDefinitionReader

UNIT_WEIGHT = Decimal("1.0000000000")
CompletenessStatus = Literal["COMPLETE", "PARTIAL"]


class BenchmarkDefinitionService:
    """Resolve benchmark definition evidence through a persistence-independent port."""

    def __init__(
        self,
        *,
        reader: BenchmarkDefinitionReader,
        clock: Callable[[], datetime],
    ) -> None:
        self._reader = reader
        self._clock = clock

    async def resolve(
        self,
        *,
        benchmark_id: str,
        request: BenchmarkDefinitionRequest,
    ) -> BenchmarkDefinitionResponse | None:
        definition = await self._reader.resolve_definition(
            benchmark_id=benchmark_id,
            as_of_date=request.as_of_date,
        )
        if definition is None:
            return None
        components = await self._reader.list_components(
            benchmark_id=benchmark_id,
            as_of_date=request.as_of_date,
        )
        return build_benchmark_definition_response(
            definition=definition,
            components=components,
            request=request,
            generated_at=self._clock(),
        )


def build_benchmark_definition_response(
    *,
    definition: BenchmarkDefinitionEvidence,
    components: list[BenchmarkComponentEvidence],
    request: BenchmarkDefinitionRequest,
    generated_at: datetime,
) -> BenchmarkDefinitionResponse:
    """Build a deterministic benchmark definition and its completeness evidence."""

    total_weight = sum(
        (component.composition_weight for component in components),
        start=Decimal("0.0000000000"),
    )
    completeness_status, completeness_reason = _completeness(
        component_count=len(components),
        total_weight=total_weight,
    )
    latest_evidence = max(
        timestamp
        for timestamp in (
            definition.source_timestamp,
            definition.updated_at,
            definition.created_at,
            *(
                timestamp
                for component in components
                for timestamp in (
                    component.source_timestamp,
                    component.updated_at,
                    component.created_at,
                )
            ),
        )
        if timestamp is not None
    )
    content_hash = stable_content_hash(
        {
            "product_name": "BenchmarkDefinition",
            "product_version": "v1",
            "as_of_date": request.as_of_date,
            "definition": asdict(definition),
            "components": [asdict(component) for component in components],
            "completeness_status": completeness_status,
            "completeness_reason": completeness_reason,
            "total_component_weight": total_weight,
            "latest_evidence_timestamp": latest_evidence,
        }
    )
    quality_complete = completeness_status == "COMPLETE" and _accepted_quality(
        definition, components
    )
    metadata = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.as_of_date,
        data_quality_status="COMPLETE" if quality_complete else "PARTIAL",
        latest_evidence_timestamp=latest_evidence,
        content_hash=content_hash,
        source_refs=[
            "lotus-core://source/BenchmarkDefinition/"
            f"{definition.benchmark_id}/{request.as_of_date.isoformat()}"
        ],
        lineage={
            "source_owner": "lotus-core",
            "source_product": "BenchmarkDefinition",
            "benchmark_id": definition.benchmark_id,
            "source_system": definition.source_vendor or "lotus-core",
            "source_record_id": definition.source_record_id,
        },
        source_evidence_current=quality_complete,
        freshness_status="CURRENT" if quality_complete else "PARTIAL",
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return BenchmarkDefinitionResponse(
        benchmark_id=definition.benchmark_id,
        benchmark_name=definition.benchmark_name,
        benchmark_type=definition.benchmark_type,
        benchmark_currency=definition.benchmark_currency,
        return_convention=definition.return_convention,
        benchmark_status=definition.benchmark_status,
        benchmark_family=definition.benchmark_family,
        benchmark_provider=definition.benchmark_provider,
        rebalance_frequency=definition.rebalance_frequency,
        classification_set_id=definition.classification_set_id,
        classification_labels=dict(definition.classification_labels),
        effective_from=definition.effective_from,
        effective_to=definition.effective_to,
        quality_status=definition.quality_status,
        source_timestamp=definition.source_timestamp,
        source_vendor=definition.source_vendor,
        source_record_id=definition.source_record_id,
        components=[_component_response(component) for component in components],
        completeness_status=completeness_status,
        completeness_reason=completeness_reason,
        total_component_weight=total_weight,
        **metadata,
    )


def _component_response(component: BenchmarkComponentEvidence) -> BenchmarkComponentResponse:
    return BenchmarkComponentResponse(
        index_id=component.index_id,
        composition_weight=component.composition_weight,
        composition_effective_from=component.composition_effective_from,
        composition_effective_to=component.composition_effective_to,
        rebalance_event_id=component.rebalance_event_id,
    )


def _completeness(*, component_count: int, total_weight: Decimal) -> tuple[CompletenessStatus, str]:
    if component_count == 0:
        return "PARTIAL", "BENCHMARK_COMPONENTS_MISSING"
    if total_weight != UNIT_WEIGHT:
        return "PARTIAL", "BENCHMARK_COMPONENT_WEIGHTS_NOT_ONE"
    return "COMPLETE", "BENCHMARK_DEFINITION_COMPLETE"


def _accepted_quality(
    definition: BenchmarkDefinitionEvidence,
    components: list[BenchmarkComponentEvidence],
) -> bool:
    accepted = {"ACCEPTED", "COMPLETE"}
    return definition.quality_status.strip().upper() in accepted and all(
        component.quality_status.strip().upper() in accepted for component in components
    )
