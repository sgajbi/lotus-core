from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.reference_data_repository import (
    ReferenceDataRepository,
)


class _FakeExecuteResult:
    def __init__(self, rows: list[object]):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


@pytest.mark.asyncio
async def test_reference_data_repository_methods_cover_query_contracts() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = [
        _FakeExecuteResult([SimpleNamespace(portfolio_id="P1", benchmark_id="B1")]),
        _FakeExecuteResult([SimpleNamespace(benchmark_id="B1")]),
        _FakeExecuteResult([SimpleNamespace(benchmark_id="B1", benchmark_currency="USD")]),
        _FakeExecuteResult([SimpleNamespace(benchmark_id="B1")]),
        _FakeExecuteResult([SimpleNamespace(index_id="IDX_1")]),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1", index_id="IDX_1", composition_weight=Decimal("0.5")
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1", index_id="IDX_1", composition_weight=Decimal("0.5")
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    index_id="IDX_1", series_date=date(2026, 1, 1), quality_status="accepted"
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    index_id="IDX_1", series_date=date(2026, 1, 1), quality_status="accepted"
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1", series_date=date(2026, 1, 1), quality_status="accepted"
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    index_id="IDX_1", series_date=date(2026, 1, 1), quality_status="accepted"
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    index_id="IDX_1", series_date=date(2026, 1, 1), quality_status="accepted"
                )
            ]
        ),
        _FakeExecuteResult(
            [SimpleNamespace(series_date=date(2026, 1, 1), quality_status="accepted")]
        ),
        _FakeExecuteResult([SimpleNamespace(taxonomy_scope="index")]),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1", index_id="IDX_1", composition_weight=Decimal("0.5")
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1", index_id="IDX_1", composition_weight=Decimal("0.5")
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    index_id="IDX_1", series_date=date(2026, 1, 1), quality_status="accepted"
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1", series_date=date(2026, 1, 1), quality_status="accepted"
                )
            ]
        ),
        _FakeExecuteResult(
            [SimpleNamespace(series_date=date(2026, 1, 1), quality_status="accepted")]
        ),
        _FakeExecuteResult([SimpleNamespace(rate_date=date(2026, 1, 1), rate=Decimal("1.1"))]),
    ]

    repo = ReferenceDataRepository(db)

    assert await repo.resolve_benchmark_assignment("P1", date(2026, 1, 1)) is not None
    assert await repo.get_benchmark_definition("B1", date(2026, 1, 1)) is not None
    assert await repo.list_benchmark_definitions_overlapping_window(
        "B1", date(2026, 1, 1), date(2026, 1, 2)
    )
    assert await repo.list_benchmark_definitions(date(2026, 1, 1), "composite", "USD", "active")
    assert await repo.list_index_definitions(date(2026, 1, 1), "USD", "equity", "active")
    assert await repo.list_benchmark_components("B1", date(2026, 1, 1))
    assert await repo.list_benchmark_components_overlapping_window(
        "B1", date(2026, 1, 1), date(2026, 1, 2)
    )
    assert await repo.list_index_price_points(["IDX_1"], date(2026, 1, 1), date(2026, 1, 2))
    assert await repo.list_index_return_points(["IDX_1"], date(2026, 1, 1), date(2026, 1, 2))
    assert await repo.list_index_price_points([], date(2026, 1, 1), date(2026, 1, 2)) == []
    assert await repo.list_index_return_points([], date(2026, 1, 1), date(2026, 1, 2)) == []
    assert await repo.list_benchmark_return_points("B1", date(2026, 1, 1), date(2026, 1, 2))
    assert await repo.list_index_price_series("IDX_1", date(2026, 1, 1), date(2026, 1, 2))
    assert await repo.list_index_return_series("IDX_1", date(2026, 1, 1), date(2026, 1, 2))
    assert await repo.list_risk_free_series("USD", date(2026, 1, 1), date(2026, 1, 2))
    assert await repo.list_taxonomy(date(2026, 1, 1), taxonomy_scope="index")
    grouped_components = await repo.list_benchmark_components_for_benchmarks(
        benchmark_ids=["B1"],
        as_of_date=date(2026, 1, 1),
    )
    assert grouped_components["B1"][0].index_id == "IDX_1"

    benchmark_coverage = await repo.get_benchmark_coverage(
        benchmark_id="B1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )
    assert benchmark_coverage["total_points"] >= 0

    risk_free_coverage = await repo.get_risk_free_coverage(
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )
    assert risk_free_coverage["total_points"] >= 0

    fx_rates = await repo.get_fx_rates(
        from_currency="EUR",
        to_currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )
    assert fx_rates[date(2026, 1, 1)] == Decimal("1.1")


@pytest.mark.asyncio
async def test_get_benchmark_coverage_uses_overlapping_composition_dates() -> None:
    repo = ReferenceDataRepository(AsyncMock(spec=AsyncSession))
    repo.list_benchmark_components_overlapping_window = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(
                index_id="IDX_A",
                composition_effective_from=date(2026, 1, 1),
                composition_effective_to=date(2026, 1, 1),
            ),
            SimpleNamespace(
                index_id="IDX_B",
                composition_effective_from=date(2026, 1, 2),
                composition_effective_to=date(2026, 1, 2),
            ),
        ]
    )
    repo.list_index_price_points = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(
                index_id="IDX_A",
                series_date=date(2026, 1, 1),
                quality_status="accepted",
            ),
            SimpleNamespace(
                index_id="IDX_B",
                series_date=date(2026, 1, 2),
                quality_status="accepted",
            ),
        ]
    )
    repo.list_benchmark_return_points = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(series_date=date(2026, 1, 1), quality_status="accepted"),
            SimpleNamespace(series_date=date(2026, 1, 2), quality_status="accepted"),
        ]
    )

    coverage = await repo.get_benchmark_coverage("B1", date(2026, 1, 1), date(2026, 1, 2))

    assert coverage["observed_dates"] == [date(2026, 1, 1), date(2026, 1, 2)]
    assert coverage["observed_start_date"] == date(2026, 1, 1)
    assert coverage["observed_end_date"] == date(2026, 1, 2)


@pytest.mark.asyncio
async def test_get_benchmark_coverage_marks_internal_gap_when_component_missing() -> None:
    repo = ReferenceDataRepository(AsyncMock(spec=AsyncSession))
    repo.list_benchmark_components_overlapping_window = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(
                index_id="IDX_A",
                composition_effective_from=date(2026, 1, 1),
                composition_effective_to=date(2026, 1, 3),
            )
        ]
    )
    repo.list_index_price_points = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(
                index_id="IDX_A",
                series_date=date(2026, 1, 1),
                quality_status="accepted",
            ),
            SimpleNamespace(
                index_id="IDX_A",
                series_date=date(2026, 1, 3),
                quality_status="accepted",
            ),
        ]
    )
    repo.list_benchmark_return_points = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(series_date=date(2026, 1, 1), quality_status="accepted"),
            SimpleNamespace(series_date=date(2026, 1, 2), quality_status="accepted"),
            SimpleNamespace(series_date=date(2026, 1, 3), quality_status="accepted"),
        ]
    )

    coverage = await repo.get_benchmark_coverage("B1", date(2026, 1, 1), date(2026, 1, 3))

    assert coverage["observed_dates"] == [date(2026, 1, 1), date(2026, 1, 3)]


@pytest.mark.asyncio
async def test_list_risk_free_series_canonicalizes_duplicate_dates() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(
        [
            SimpleNamespace(
                series_date=date(2026, 1, 1),
                quality_status="accepted",
                source_timestamp=None,
                risk_free_curve_id="USD_FRONT_OFFICE",
                series_id="front_office",
            ),
            SimpleNamespace(
                series_date=date(2026, 1, 1),
                quality_status="accepted",
                source_timestamp=None,
                risk_free_curve_id="USD_DEMO",
                series_id="demo",
            ),
            SimpleNamespace(
                series_date=date(2026, 1, 2),
                quality_status="accepted",
                source_timestamp=None,
                risk_free_curve_id="USD_DEMO",
                series_id="demo",
            ),
        ]
    )

    repo = ReferenceDataRepository(db)

    rows = await repo.list_risk_free_series("USD", date(2026, 1, 1), date(2026, 1, 2))

    assert [row.series_date for row in rows] == [date(2026, 1, 1), date(2026, 1, 2)]
    assert rows[0].series_id == "front_office"
    assert rows[1].series_id == "demo"
