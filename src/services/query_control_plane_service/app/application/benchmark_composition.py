"""Application use case for benchmark constituent-window evidence."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.benchmark_composition import (
    BenchmarkCompositionDateWindow,
    BenchmarkCompositionWindowRequest,
    BenchmarkCompositionWindowResponse,
    BenchmarkConstituentSegmentResponse,
)
from ..domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)
from ..ports.benchmark_definition import BenchmarkDefinitionReader
from .benchmark_component_segments import resolve_benchmark_component_segments

CompletenessStatus = Literal["COMPLETE", "PARTIAL"]
UNIT_WEIGHT = Decimal("1.0000000000")


class BenchmarkCompositionService:
    """Resolve cross-rebalance composition through the benchmark reference port."""

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
        request: BenchmarkCompositionWindowRequest,
    ) -> BenchmarkCompositionWindowResponse | None:
        definitions = await self._reader.list_definitions_overlapping_window(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        if not definitions:
            return None
        components = await self._reader.list_components_overlapping_window(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_benchmark_composition_response(
            benchmark_id=benchmark_id,
            request=request,
            definitions=definitions,
            components=components,
            generated_at=self._clock(),
        )


def build_benchmark_composition_response(
    *,
    benchmark_id: str,
    request: BenchmarkCompositionWindowRequest,
    definitions: list[BenchmarkDefinitionEvidence],
    components: list[BenchmarkComponentEvidence],
    generated_at: datetime,
) -> BenchmarkCompositionWindowResponse:
    """Resolve segment boundaries and build deterministic cross-window source proof."""

    currencies = {definition.benchmark_currency for definition in definitions}
    if len(currencies) != 1:
        raise ValueError(
            "Benchmark definition currency changed within requested composition window."
        )
    segments = resolve_benchmark_component_segments(
        components,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    incomplete_starts = _incomplete_period_starts(
        segments,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    completeness_status, completeness_reason = _completeness(incomplete_starts)
    latest_evidence = _latest_evidence(definitions, segments)
    quality_complete = completeness_status == "COMPLETE" and _accepted_quality(
        definitions, segments
    )
    content_hash = stable_content_hash(
        {
            "product_name": "BenchmarkConstituentWindow",
            "product_version": "v1",
            "benchmark_id": benchmark_id,
            "benchmark_currency": next(iter(currencies)),
            "window": request.window.model_dump(mode="json"),
            "definitions": [asdict(definition) for definition in definitions],
            "segments": [asdict(segment) for segment in segments],
            "completeness_status": completeness_status,
            "incomplete_period_starts": incomplete_starts,
            "latest_evidence_timestamp": latest_evidence,
        }
    )
    metadata = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.window.end_date,
        data_quality_status="COMPLETE" if quality_complete else "PARTIAL",
        latest_evidence_timestamp=latest_evidence,
        content_hash=content_hash,
        source_refs=[
            "lotus-core://source/BenchmarkConstituentWindow/"
            f"{benchmark_id}/{request.window.start_date.isoformat()}/"
            f"{request.window.end_date.isoformat()}"
        ],
        lineage={
            "source_owner": "lotus-core",
            "source_product": "BenchmarkConstituentWindow",
            "benchmark_id": benchmark_id,
            "contract_version": "rfc_062_v1",
        },
        source_evidence_current=quality_complete,
        freshness_status="CURRENT" if quality_complete else "PARTIAL",
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return BenchmarkCompositionWindowResponse(
        benchmark_id=benchmark_id,
        benchmark_currency=next(iter(currencies)),
        resolved_window=BenchmarkCompositionDateWindow(
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        segments=[_segment_response(segment) for segment in segments],
        completeness_status=completeness_status,
        completeness_reason=completeness_reason,
        incomplete_period_starts=incomplete_starts,
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core",
            "generated_by": "query_control_plane_service",
        },
        **metadata,
    )


def _incomplete_period_starts(
    segments: list[BenchmarkComponentEvidence],
    *,
    start_date: date,
    end_date: date,
) -> list[date]:
    boundaries = {start_date}
    boundaries.update(
        segment.composition_effective_from
        for segment in segments
        if start_date <= segment.composition_effective_from <= end_date
    )
    return [
        boundary
        for boundary in sorted(boundaries)
        if sum(
            (
                segment.composition_weight
                for segment in segments
                if segment.composition_effective_from <= boundary
                and (
                    segment.composition_effective_to is None
                    or segment.composition_effective_to >= boundary
                )
            ),
            start=Decimal("0.0000000000"),
        )
        != UNIT_WEIGHT
    ]


def _completeness(incomplete_starts: list[date]) -> tuple[CompletenessStatus, str]:
    if incomplete_starts:
        return "PARTIAL", "BENCHMARK_COMPOSITION_WEIGHTS_INCOMPLETE"
    return "COMPLETE", "BENCHMARK_COMPOSITION_WINDOW_COMPLETE"


def _latest_evidence(
    definitions: list[BenchmarkDefinitionEvidence],
    components: list[BenchmarkComponentEvidence],
) -> datetime | None:
    timestamps = [
        timestamp
        for definition in definitions
        for timestamp in (
            definition.source_timestamp,
            definition.updated_at,
            definition.created_at,
        )
        if timestamp is not None
    ]
    timestamps.extend(
        timestamp
        for component in components
        for timestamp in (
            component.source_timestamp,
            component.updated_at,
            component.created_at,
        )
        if timestamp is not None
    )
    return max(timestamps) if timestamps else None


def _accepted_quality(
    definitions: list[BenchmarkDefinitionEvidence],
    components: list[BenchmarkComponentEvidence],
) -> bool:
    accepted = {"ACCEPTED", "COMPLETE"}
    return all(row.quality_status.strip().upper() in accepted for row in definitions) and all(
        row.quality_status.strip().upper() in accepted for row in components
    )


def _segment_response(
    segment: BenchmarkComponentEvidence,
) -> BenchmarkConstituentSegmentResponse:
    return BenchmarkConstituentSegmentResponse(
        index_id=segment.index_id,
        composition_weight=segment.composition_weight,
        composition_effective_from=segment.composition_effective_from,
        composition_effective_to=segment.composition_effective_to,
        rebalance_event_id=segment.rebalance_event_id,
    )
