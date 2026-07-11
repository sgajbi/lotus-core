"""Application tests for benchmark constituent-window evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.benchmark_composition import (
    BenchmarkCompositionService,
    build_benchmark_composition_response,
)
from src.services.query_control_plane_service.app.contracts.benchmark_composition import (
    BenchmarkCompositionWindowRequest,
)
from src.services.query_control_plane_service.app.domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)
REQUEST = BenchmarkCompositionWindowRequest(
    window={"start_date": date(2026, 1, 15), "end_date": date(2026, 3, 31)}
)


def _definition(*, currency: str = "USD") -> BenchmarkDefinitionEvidence:
    return BenchmarkDefinitionEvidence(
        benchmark_id="BMK_GLOBAL_BALANCED",
        benchmark_name="Global Balanced",
        benchmark_type="composite",
        benchmark_currency=currency,
        return_convention="total_return_index",
        benchmark_status="active",
        benchmark_family="multi_asset",
        benchmark_provider="provider",
        rebalance_frequency="quarterly",
        classification_set_id=None,
        classification_labels={},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
        source_vendor="provider",
        source_record_id="definition:1",
        quality_status="accepted",
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=EVIDENCE_AT,
    )


def _component(
    index_id: str,
    weight: str,
    effective_from: date,
    *,
    effective_to: date | None = None,
) -> BenchmarkComponentEvidence:
    return BenchmarkComponentEvidence(
        benchmark_id="BMK_GLOBAL_BALANCED",
        index_id=index_id,
        composition_effective_from=effective_from,
        composition_effective_to=effective_to,
        composition_weight=Decimal(weight),
        rebalance_event_id=f"rebalance:{effective_from.isoformat()}",
        source_timestamp=datetime(2026, 4, 10, 9, 30, tzinfo=UTC),
        source_vendor="provider",
        source_record_id=f"component:{index_id}:{effective_from.isoformat()}",
        quality_status="accepted",
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=EVIDENCE_AT,
    )


def _complete_components() -> list[BenchmarkComponentEvidence]:
    return [
        _component("IDX_EQ", "0.6000000000", date(2026, 1, 1)),
        _component("IDX_FI", "0.4000000000", date(2026, 1, 1)),
        _component("IDX_EQ", "0.5500000000", date(2026, 2, 1)),
        _component("IDX_FI", "0.4500000000", date(2026, 2, 1)),
    ]


def _build(
    components: list[BenchmarkComponentEvidence],
    *,
    definitions: list[BenchmarkDefinitionEvidence] | None = None,
    generated_at: datetime = GENERATED_AT,
):
    return build_benchmark_composition_response(
        benchmark_id="BMK_GLOBAL_BALANCED",
        request=REQUEST,
        definitions=definitions or [_definition()],
        components=components,
        generated_at=generated_at,
    )


def test_rebalance_boundaries_are_inferred_and_complete() -> None:
    response = _build(_complete_components())

    assert response.completeness_status == "COMPLETE"
    assert response.completeness_reason == "BENCHMARK_COMPOSITION_WINDOW_COMPLETE"
    assert response.incomplete_period_starts == []
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.source_batch_fingerprint == response.content_hash == response.source_digest
    assert [
        (segment.index_id, segment.composition_effective_from, segment.composition_effective_to)
        for segment in response.segments
    ] == [
        ("IDX_EQ", date(2026, 1, 1), date(2026, 1, 31)),
        ("IDX_FI", date(2026, 1, 1), date(2026, 1, 31)),
        ("IDX_EQ", date(2026, 2, 1), None),
        ("IDX_FI", date(2026, 2, 1), None),
    ]


def test_incomplete_rebalance_period_is_reported_and_not_current() -> None:
    components = _complete_components()
    components.pop()

    response = _build(components)

    assert response.completeness_status == "PARTIAL"
    assert response.completeness_reason == "BENCHMARK_COMPOSITION_WEIGHTS_INCOMPLETE"
    assert response.incomplete_period_starts == [date(2026, 2, 1)]
    assert response.data_quality_status == "PARTIAL"
    assert response.source_evidence_current is False


def test_missing_initial_period_is_reported_at_requested_start() -> None:
    response = _build(
        [
            _component("IDX_EQ", "0.6000000000", date(2026, 2, 1)),
            _component("IDX_FI", "0.4000000000", date(2026, 2, 1)),
        ]
    )

    assert response.incomplete_period_starts == [date(2026, 1, 15)]


def test_currency_drift_is_rejected() -> None:
    with pytest.raises(ValueError, match="currency changed within requested composition window"):
        _build(
            _complete_components(),
            definitions=[_definition(currency="USD"), _definition(currency="EUR")],
        )


def test_content_hash_excludes_generated_at() -> None:
    first = _build(_complete_components())
    second = _build(
        _complete_components(),
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.generated_at != second.generated_at
    assert first.content_hash == second.content_hash


@pytest.mark.asyncio
async def test_service_skips_component_read_without_definition() -> None:
    class Reader:
        async def list_definitions_overlapping_window(self, **_: object) -> list[object]:
            return []

        async def list_components_overlapping_window(self, **_: object) -> list[object]:
            raise AssertionError("components must not be read without a definition")

    response = await BenchmarkCompositionService(
        reader=Reader(),  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).resolve(benchmark_id="BMK_UNKNOWN", request=REQUEST)

    assert response is None
