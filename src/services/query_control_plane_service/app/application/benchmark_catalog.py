"""Application use case for the effective benchmark definition catalog."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.benchmark_catalog import (
    BenchmarkCatalogRecord,
    BenchmarkCatalogRequest,
    BenchmarkCatalogResponse,
)
from ..contracts.benchmark_definition import BenchmarkComponentResponse
from ..domain.benchmark_definition import BenchmarkComponentEvidence, BenchmarkDefinitionEvidence
from ..ports.benchmark_definition import BenchmarkDefinitionReader

CatalogCompleteness = Literal["COMPLETE", "PARTIAL", "EMPTY"]
UNIT_WEIGHT = Decimal("1.0000000000")


class BenchmarkCatalogService:
    """Resolve effective benchmark definitions and constituents through one bounded port."""

    def __init__(self, *, reader: BenchmarkDefinitionReader, clock: Callable[[], datetime]) -> None:
        self._reader = reader
        self._clock = clock

    async def list(self, *, request: BenchmarkCatalogRequest) -> BenchmarkCatalogResponse:
        definitions = await self._reader.list_definitions(
            as_of_date=request.as_of_date,
            benchmark_type=request.benchmark_type,
            benchmark_currency=request.benchmark_currency,
            benchmark_status=request.benchmark_status,
        )
        components = await self._reader.list_components_for_benchmarks(
            benchmark_ids=[definition.benchmark_id for definition in definitions],
            as_of_date=request.as_of_date,
        )
        return build_benchmark_catalog_response(
            request=request,
            definitions=definitions,
            components_by_benchmark=components,
            generated_at=self._clock(),
        )


def build_benchmark_catalog_response(
    *,
    request: BenchmarkCatalogRequest,
    definitions: list[BenchmarkDefinitionEvidence],
    components_by_benchmark: dict[str, list[BenchmarkComponentEvidence]],
    generated_at: datetime,
) -> BenchmarkCatalogResponse:
    """Build ordered records and collection-level deterministic source proof."""

    records = [
        _catalog_record(definition, components_by_benchmark.get(definition.benchmark_id, []))
        for definition in definitions
    ]
    completeness = _catalog_completeness(records)
    evidence = [component for rows in components_by_benchmark.values() for component in rows]
    latest_evidence = _latest_evidence(definitions, evidence)
    quality_complete = completeness == "COMPLETE" and _accepted_quality(definitions, evidence)
    content_hash = stable_content_hash(
        {
            "product_name": "BenchmarkDefinition",
            "product_version": "v1",
            "request": request.model_dump(mode="json"),
            "definitions": [asdict(definition) for definition in definitions],
            "components": {
                key: [asdict(component) for component in value]
                for key, value in sorted(components_by_benchmark.items())
            },
            "completeness_status": completeness,
            "latest_evidence_timestamp": latest_evidence,
        }
    )
    metadata = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.as_of_date,
        data_quality_status=(
            "COMPLETE" if quality_complete else "EMPTY" if not records else "PARTIAL"
        ),
        latest_evidence_timestamp=latest_evidence,
        content_hash=content_hash,
        source_refs=[
            f"lotus-core://source/BenchmarkDefinition/catalog/{request.as_of_date.isoformat()}"
        ],
        lineage={
            "source_owner": "lotus-core",
            "source_product": "BenchmarkDefinition",
            "catalog_scope": "effective_definitions",
        },
        source_evidence_current=quality_complete,
        freshness_status="CURRENT"
        if quality_complete
        else "UNAVAILABLE"
        if not records
        else "PARTIAL",
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return BenchmarkCatalogResponse(
        records=records,
        record_count=len(records),
        completeness_status=completeness,
        **metadata,
    )


def _catalog_record(
    definition: BenchmarkDefinitionEvidence,
    components: list[BenchmarkComponentEvidence],
) -> BenchmarkCatalogRecord:
    total_weight = sum(
        (row.composition_weight for row in components), start=Decimal("0.0000000000")
    )
    if not components:
        status, reason = "PARTIAL", "BENCHMARK_COMPONENTS_MISSING"
    elif total_weight != UNIT_WEIGHT:
        status, reason = "PARTIAL", "BENCHMARK_COMPONENT_WEIGHTS_NOT_ONE"
    else:
        status, reason = "COMPLETE", "BENCHMARK_DEFINITION_COMPLETE"
    return BenchmarkCatalogRecord(
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
        components=[
            BenchmarkComponentResponse(
                index_id=row.index_id,
                composition_weight=row.composition_weight,
                composition_effective_from=row.composition_effective_from,
                composition_effective_to=row.composition_effective_to,
                rebalance_event_id=row.rebalance_event_id,
            )
            for row in components
        ],
        completeness_status=status,
        completeness_reason=reason,
        total_component_weight=total_weight,
    )


def _catalog_completeness(records: list[BenchmarkCatalogRecord]) -> CatalogCompleteness:
    if not records:
        return "EMPTY"
    return (
        "COMPLETE"
        if all(record.completeness_status == "COMPLETE" for record in records)
        else "PARTIAL"
    )


def _latest_evidence(
    definitions: list[BenchmarkDefinitionEvidence], components: list[BenchmarkComponentEvidence]
) -> datetime | None:
    timestamps = [
        timestamp
        for definition in definitions
        for timestamp in (definition.source_timestamp, definition.updated_at, definition.created_at)
        if timestamp is not None
    ]
    timestamps.extend(
        timestamp
        for component in components
        for timestamp in (component.source_timestamp, component.updated_at, component.created_at)
        if timestamp is not None
    )
    return max(timestamps) if timestamps else None


def _accepted_quality(
    definitions: list[BenchmarkDefinitionEvidence], components: list[BenchmarkComponentEvidence]
) -> bool:
    accepted = {"ACCEPTED", "COMPLETE"}
    return all(row.quality_status.strip().upper() in accepted for row in definitions) and all(
        row.quality_status.strip().upper() in accepted for row in components
    )
