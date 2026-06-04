import asyncio
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkCompositionWindowRequest,
)
from src.services.query_service.app.services.benchmark_composition import (
    benchmark_composition_definition_context,
    build_benchmark_composition_window_response,
    resolve_benchmark_composition_window_response,
)


def test_benchmark_composition_definition_context_returns_none_without_definitions() -> None:
    assert benchmark_composition_definition_context([]) is None


def test_benchmark_composition_definition_context_rejects_currency_drift() -> None:
    with pytest.raises(ValueError, match="currency changed within requested composition window"):
        benchmark_composition_definition_context(
            [
                SimpleNamespace(
                    benchmark_id="BMK_GLOBAL_BALANCED",
                    benchmark_currency="USD",
                    effective_from=date(2026, 1, 1),
                ),
                SimpleNamespace(
                    benchmark_id="BMK_GLOBAL_BALANCED",
                    benchmark_currency="EUR",
                    effective_from=date(2026, 2, 1),
                ),
            ]
        )


def test_resolve_benchmark_composition_window_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def list_benchmark_definitions_overlapping_window(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("definitions", kwargs))
                return [
                    SimpleNamespace(
                        benchmark_id="BMK_GLOBAL_BALANCED",
                        benchmark_currency="USD",
                        effective_from=date(2026, 1, 1),
                        quality_status="accepted",
                        source_timestamp=datetime(2026, 1, 31, 9, 0, 0),
                    )
                ]

            async def list_benchmark_components_overlapping_window(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("components", kwargs))
                return [
                    SimpleNamespace(
                        index_id="IDX_EQ",
                        composition_weight=Decimal("0.6000000000"),
                        composition_effective_from=date(2026, 1, 1),
                        composition_effective_to=None,
                        rebalance_event_id="rebalance_2026_01",
                        quality_status="accepted",
                        source_timestamp=datetime(2026, 2, 1, 9, 30, 0),
                    )
                ]

        response = await resolve_benchmark_composition_window_response(
            repository=Repository(),
            benchmark_id="BMK_GLOBAL_BALANCED",
            request=BenchmarkCompositionWindowRequest(
                window={"start_date": date(2026, 1, 15), "end_date": date(2026, 3, 31)}
            ),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is not None
    assert response.benchmark_currency == "USD"
    assert [segment.index_id for segment in response.segments] == ["IDX_EQ"]
    assert calls == [
        (
            "definitions",
            {
                "benchmark_id": "BMK_GLOBAL_BALANCED",
                "start_date": date(2026, 1, 15),
                "end_date": date(2026, 3, 31),
            },
        ),
        (
            "components",
            {
                "benchmark_id": "BMK_GLOBAL_BALANCED",
                "start_date": date(2026, 1, 15),
                "end_date": date(2026, 3, 31),
            },
        ),
    ]


def test_resolve_benchmark_composition_window_response_skips_components_without_definition() -> (
    None
):
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def list_benchmark_definitions_overlapping_window(
                self, **_: object
            ) -> list[object]:
                calls.append("definitions")
                return []

            async def list_benchmark_components_overlapping_window(
                self, **_: object
            ) -> list[object]:
                calls.append("components")
                raise AssertionError("Unexpected component read without benchmark definition")

        response = await resolve_benchmark_composition_window_response(
            repository=Repository(),
            benchmark_id="BMK_UNKNOWN",
            request=BenchmarkCompositionWindowRequest(
                window={"start_date": date(2026, 1, 15), "end_date": date(2026, 3, 31)}
            ),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["definitions"]


def test_build_benchmark_composition_window_response_resolves_segments_and_metadata() -> None:
    definition_context = benchmark_composition_definition_context(
        [
            SimpleNamespace(
                benchmark_id="BMK_GLOBAL_BALANCED",
                benchmark_currency="USD",
                effective_from=date(2025, 1, 1),
                quality_status="accepted",
                source_timestamp=datetime(2026, 1, 31, 9, 0, 0),
            ),
            SimpleNamespace(
                benchmark_id="BMK_GLOBAL_BALANCED",
                benchmark_currency="USD",
                effective_from=date(2026, 1, 1),
                quality_status="accepted",
                source_timestamp=datetime(2026, 2, 1, 9, 0, 0),
            ),
        ]
    )
    assert definition_context is not None

    response = build_benchmark_composition_window_response(
        benchmark_id="BMK_GLOBAL_BALANCED",
        request=BenchmarkCompositionWindowRequest(
            window={"start_date": date(2026, 1, 15), "end_date": date(2026, 3, 31)}
        ),
        definition_context=definition_context,
        component_rows=[
            SimpleNamespace(
                index_id="IDX_EQ",
                composition_weight=Decimal("0.6000000000"),
                composition_effective_from=date(2025, 1, 1),
                composition_effective_to=None,
                rebalance_event_id="old",
                quality_status="accepted",
                source_timestamp=datetime(2026, 1, 15, 9, 0, 0),
            ),
            SimpleNamespace(
                index_id="IDX_EQ",
                composition_weight=Decimal("0.5500000000"),
                composition_effective_from=date(2026, 2, 1),
                composition_effective_to=None,
                rebalance_event_id="rebalance_2026_02",
                quality_status="accepted",
                source_timestamp=datetime(2026, 2, 1, 9, 30, 0),
            ),
            SimpleNamespace(
                index_id="IDX_FI",
                composition_weight=Decimal("0.4500000000"),
                composition_effective_from=date(2026, 2, 1),
                composition_effective_to=None,
                rebalance_event_id="rebalance_2026_02",
                quality_status="accepted",
                source_timestamp=datetime(2026, 2, 1, 9, 30, 0),
            ),
        ],
    )

    assert response.product_name == "BenchmarkConstituentWindow"
    assert response.benchmark_id == "BMK_GLOBAL_BALANCED"
    assert response.benchmark_currency == "USD"
    resolved_segments = [
        (segment.index_id, segment.composition_effective_to) for segment in response.segments
    ]
    assert resolved_segments == [
        ("IDX_EQ", date(2026, 1, 31)),
        ("IDX_EQ", None),
        ("IDX_FI", None),
    ]
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == datetime(2026, 2, 1, 9, 30, 0)
    assert response.lineage == {
        "contract_version": "rfc_062_v1",
        "source_system": "lotus-core-query-service",
        "generated_by": "integration.benchmark_composition_window",
    }
