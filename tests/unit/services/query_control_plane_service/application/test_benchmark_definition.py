"""Application tests for effective benchmark definition evidence."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.benchmark_definition import (
    BenchmarkDefinitionService,
    build_benchmark_definition_response,
)
from src.services.query_control_plane_service.app.contracts.benchmark_definition import (
    BenchmarkDefinitionRequest,
)
from src.services.query_control_plane_service.app.domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)
REQUEST = BenchmarkDefinitionRequest(as_of_date=date(2026, 4, 10))


def _definition() -> BenchmarkDefinitionEvidence:
    return BenchmarkDefinitionEvidence(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        benchmark_name="Global Balanced 60/40",
        benchmark_type="composite",
        benchmark_currency="SGD",
        return_convention="total_return_index",
        benchmark_status="active",
        benchmark_family="multi_asset",
        benchmark_provider="lotus-investment-office",
        rebalance_frequency="quarterly",
        classification_set_id="wm_global_taxonomy_v1",
        classification_labels={"asset_class": "multi_asset", "region": "global"},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
        source_vendor="lotus-investment-office",
        source_record_id="benchmark:balanced:2026",
        quality_status="accepted",
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=EVIDENCE_AT,
    )


def _component(index_id: str, weight: str) -> BenchmarkComponentEvidence:
    return BenchmarkComponentEvidence(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        index_id=index_id,
        composition_effective_from=date(2026, 1, 1),
        composition_effective_to=None,
        composition_weight=Decimal(weight),
        rebalance_event_id="rebalance_2026q1",
        source_timestamp=datetime(2026, 4, 10, 9, 30, tzinfo=UTC),
        source_vendor="lotus-investment-office",
        source_record_id=f"component:{index_id}:2026",
        quality_status="accepted",
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=EVIDENCE_AT,
    )


def _build(
    components: list[BenchmarkComponentEvidence],
    *,
    definition: BenchmarkDefinitionEvidence | None = None,
):
    return build_benchmark_definition_response(
        definition=definition or _definition(),
        components=components,
        request=REQUEST,
        generated_at=GENERATED_AT,
    )


def test_unit_weight_definition_is_complete_current_and_deterministic() -> None:
    response = _build(
        [
            _component("IDX_GLOBAL_EQUITY", "0.6000000000"),
            _component("IDX_GLOBAL_BOND", "0.4000000000"),
        ]
    )

    assert response.completeness_status == "COMPLETE"
    assert response.completeness_reason == "BENCHMARK_DEFINITION_COMPLETE"
    assert response.total_component_weight == Decimal("1.0000000000")
    assert response.data_quality_status == "COMPLETE"
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.latest_evidence_timestamp == EVIDENCE_AT
    assert response.source_batch_fingerprint == response.content_hash == response.source_digest
    assert [component.index_id for component in response.components] == [
        "IDX_GLOBAL_EQUITY",
        "IDX_GLOBAL_BOND",
    ]


def test_missing_components_are_partial_and_not_current() -> None:
    response = _build([])

    assert response.completeness_status == "PARTIAL"
    assert response.completeness_reason == "BENCHMARK_COMPONENTS_MISSING"
    assert response.data_quality_status == "PARTIAL"
    assert response.source_evidence_current is False
    assert response.freshness_status == "PARTIAL"


def test_non_unit_component_weights_are_partial() -> None:
    response = _build([_component("IDX_GLOBAL_EQUITY", "0.6000000000")])

    assert response.completeness_reason == "BENCHMARK_COMPONENT_WEIGHTS_NOT_ONE"
    assert response.total_component_weight == Decimal("0.6000000000")
    assert response.source_evidence_current is False


def test_non_accepted_source_quality_prevents_current_evidence() -> None:
    response = _build(
        [_component("IDX_GLOBAL", "1.0000000000")],
        definition=replace(_definition(), quality_status="stale"),
    )

    assert response.completeness_status == "COMPLETE"
    assert response.data_quality_status == "PARTIAL"
    assert response.source_evidence_current is False


def test_content_hash_excludes_generated_at() -> None:
    components = [_component("IDX_GLOBAL", "1.0000000000")]
    first = _build(components)
    second = build_benchmark_definition_response(
        definition=_definition(),
        components=components,
        request=REQUEST,
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.generated_at != second.generated_at
    assert first.content_hash == second.content_hash


@pytest.mark.asyncio
async def test_service_resolves_definition_before_components() -> None:
    class Reader:
        async def resolve_definition(self, **kwargs: object) -> BenchmarkDefinitionEvidence:
            self.definition_kwargs = kwargs
            return _definition()

        async def list_components(self, **kwargs: object) -> list[BenchmarkComponentEvidence]:
            self.component_kwargs = kwargs
            return [_component("IDX_GLOBAL", "1.0000000000")]

    reader = Reader()
    response = await BenchmarkDefinitionService(
        reader=reader,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).resolve(benchmark_id="BMK_GLOBAL_BALANCED_60_40", request=REQUEST)

    expected_scope = {
        "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
        "as_of_date": date(2026, 4, 10),
    }
    assert reader.definition_kwargs == expected_scope
    assert reader.component_kwargs == expected_scope
    assert response is not None
    assert response.completeness_status == "COMPLETE"
