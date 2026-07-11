"""Application tests for the effective benchmark definition catalog."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.benchmark_catalog import (
    BenchmarkCatalogService,
    build_benchmark_catalog_response,
)
from src.services.query_control_plane_service.app.contracts.benchmark_catalog import (
    BenchmarkCatalogRequest,
)
from src.services.query_control_plane_service.app.domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)
REQUEST = BenchmarkCatalogRequest(as_of_date=date(2026, 4, 10))


def _definition(benchmark_id: str = "BMK_1") -> BenchmarkDefinitionEvidence:
    return BenchmarkDefinitionEvidence(
        benchmark_id=benchmark_id,
        benchmark_name="Global Balanced",
        benchmark_type="composite",
        benchmark_currency="USD",
        return_convention="total_return_index",
        benchmark_status="active",
        benchmark_family="multi_asset",
        benchmark_provider="provider",
        rebalance_frequency="quarterly",
        classification_set_id="taxonomy_1",
        classification_labels={"asset_class": "multi_asset"},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
        source_vendor="provider",
        source_record_id=f"definition:{benchmark_id}",
        quality_status="accepted",
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=EVIDENCE_AT,
    )


def _component(index_id: str, weight: str) -> BenchmarkComponentEvidence:
    return BenchmarkComponentEvidence(
        benchmark_id="BMK_1",
        index_id=index_id,
        composition_effective_from=date(2026, 1, 1),
        composition_effective_to=None,
        composition_weight=Decimal(weight),
        rebalance_event_id="rebalance_1",
        source_timestamp=datetime(2026, 4, 10, 9, 30, tzinfo=UTC),
        source_vendor="provider",
        source_record_id=f"component:{index_id}",
        quality_status="accepted",
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=EVIDENCE_AT,
    )


def _build(components: list[BenchmarkComponentEvidence]):
    return build_benchmark_catalog_response(
        request=REQUEST,
        definitions=[_definition()],
        components_by_benchmark={"BMK_1": components},
        generated_at=GENERATED_AT,
    )


def test_complete_catalog_is_current_and_deterministic() -> None:
    response = _build([_component("IDX_EQ", "0.6000000000"), _component("IDX_FI", "0.4000000000")])

    assert response.record_count == 1
    assert response.completeness_status == "COMPLETE"
    assert response.records[0].total_component_weight == Decimal("1.0000000000")
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.source_batch_fingerprint == response.content_hash == response.source_digest


def test_partial_record_degrades_catalog() -> None:
    response = _build([_component("IDX_EQ", "0.6000000000")])

    assert response.completeness_status == "PARTIAL"
    assert response.records[0].completeness_reason == "BENCHMARK_COMPONENT_WEIGHTS_NOT_ONE"
    assert response.source_evidence_current is False


def test_empty_catalog_is_truthfully_unavailable() -> None:
    response = build_benchmark_catalog_response(
        request=REQUEST,
        definitions=[],
        components_by_benchmark={},
        generated_at=GENERATED_AT,
    )

    assert response.records == []
    assert response.record_count == 0
    assert response.completeness_status == "EMPTY"
    assert response.data_quality_status == "EMPTY"
    assert response.freshness_status == "UNAVAILABLE"


def test_content_hash_excludes_generated_at() -> None:
    components = [_component("IDX_ALL", "1.0000000000")]
    first = _build(components)
    second = build_benchmark_catalog_response(
        request=REQUEST,
        definitions=[_definition()],
        components_by_benchmark={"BMK_1": components},
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.generated_at != second.generated_at
    assert first.content_hash == second.content_hash


@pytest.mark.asyncio
async def test_service_propagates_all_catalog_filters() -> None:
    class Reader:
        async def list_definitions(self, **kwargs: object) -> list[BenchmarkDefinitionEvidence]:
            self.definition_kwargs = kwargs
            return [_definition()]

        async def list_components_for_benchmarks(
            self, **kwargs: object
        ) -> dict[str, list[BenchmarkComponentEvidence]]:
            self.component_kwargs = kwargs
            return {"BMK_1": [_component("IDX_ALL", "1.0000000000")]}

    reader = Reader()
    request = BenchmarkCatalogRequest(
        as_of_date=date(2026, 4, 10),
        benchmark_type="composite",
        benchmark_currency="usd",
        benchmark_status="active",
    )
    response = await BenchmarkCatalogService(
        reader=reader,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).list(request=request)

    assert reader.definition_kwargs == {
        "as_of_date": date(2026, 4, 10),
        "benchmark_type": "composite",
        "benchmark_currency": "usd",
        "benchmark_status": "active",
    }
    assert reader.component_kwargs["benchmark_ids"] == ["BMK_1"]
    assert response.records[0].benchmark_id == "BMK_1"
