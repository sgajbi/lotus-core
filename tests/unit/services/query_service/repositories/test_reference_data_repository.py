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
async def test_reference_data_repository_normalizes_market_reference_currency_filters() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = [
        _FakeExecuteResult([]),
        _FakeExecuteResult([]),
    ]
    repo = ReferenceDataRepository(db)

    await repo.list_benchmark_definitions(
        as_of_date=date(2026, 1, 31),
        benchmark_currency=" usd ",
    )
    await repo.list_risk_free_series(
        currency=" eur ",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    benchmark_sql = str(
        db.execute.await_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    risk_free_sql = str(
        db.execute.await_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True})
    )

    assert "benchmark_definitions.benchmark_currency = 'USD'" in benchmark_sql
    assert "row_number() OVER (PARTITION BY benchmark_definitions.benchmark_id" in benchmark_sql
    assert "anon_1.rn = 1" in benchmark_sql
    assert "risk_free_series.series_currency = 'EUR'" in risk_free_sql
    assert "row_number() OVER (PARTITION BY risk_free_series.series_date" in risk_free_sql
    assert "upper(trim(risk_free_series.quality_status)) = 'ACCEPTED'" in risk_free_sql
    assert "anon_1.rn = 1" in risk_free_sql


@pytest.mark.asyncio
async def test_reference_data_repository_methods_cover_query_contracts() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = [
        _FakeExecuteResult([SimpleNamespace(benchmark_id="B1")]),
        _FakeExecuteResult([SimpleNamespace(benchmark_id="B1", benchmark_currency="USD")]),
        _FakeExecuteResult([SimpleNamespace(benchmark_id="B1")]),
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
        _FakeExecuteResult(
            [
                SimpleNamespace(rate_date=date(2026, 1, 1), rate=Decimal("1.1")),
                SimpleNamespace(rate_date=date(2026, 1, 2), rate=" "),
                SimpleNamespace(rate_date=date(2026, 1, 3), rate=None),
                SimpleNamespace(rate_date=date(2026, 1, 4), rate=" 1.4 "),
            ]
        ),
    ]

    repo = ReferenceDataRepository(db)

    assert await repo.get_benchmark_definition("B1", date(2026, 1, 1)) is not None
    assert await repo.list_benchmark_definitions_overlapping_window(
        "B1", date(2026, 1, 1), date(2026, 1, 2)
    )
    assert await repo.list_benchmark_definitions(date(2026, 1, 1), "composite", "USD", "active")
    assert await repo.list_benchmark_components("B1", date(2026, 1, 1))
    benchmark_component_sql = str(
        db.execute.await_args_list[3].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert (
        "row_number() OVER (PARTITION BY benchmark_composition_series.benchmark_id, "
        "benchmark_composition_series.index_id"
    ) in benchmark_component_sql
    assert "anon_1.rn = 1" in benchmark_component_sql
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
    benchmark_components_stmt = db.execute.await_args_list[12].args[0]
    benchmark_components_sql = str(
        benchmark_components_stmt.compile(compile_kwargs={"literal_binds": True})
    )
    assert "benchmark_composition_series.benchmark_id IN ('B1')" in benchmark_components_sql
    assert "benchmark_composition_series.composition_effective_from <= '2026-01-01'" in (
        benchmark_components_sql
    )
    assert "benchmark_composition_series.composition_effective_to IS NULL" in (
        benchmark_components_sql
    )
    assert (
        "ORDER BY benchmark_composition_series.benchmark_id ASC, "
        "benchmark_composition_series.index_id ASC"
    ) in benchmark_components_sql
    assert (
        "row_number() OVER (PARTITION BY benchmark_composition_series.benchmark_id, "
        "benchmark_composition_series.index_id"
    ) in benchmark_components_sql
    assert "anon_1.rn = 1" in benchmark_components_sql

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
        from_currency=" eur ",
        to_currency=" usd ",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )
    assert fx_rates[date(2026, 1, 1)] == Decimal("1.1")
    assert date(2026, 1, 2) not in fx_rates
    assert date(2026, 1, 3) not in fx_rates
    assert fx_rates[date(2026, 1, 4)] == Decimal("1.4")
    fx_stmt = db.execute.await_args_list[17].args[0]
    fx_sql = str(fx_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "upper(trim(fx_rates.from_currency)) = 'EUR'" in fx_sql
    assert "upper(trim(fx_rates.to_currency)) = 'USD'" in fx_sql


@pytest.mark.asyncio
async def test_reference_data_repository_pages_benchmark_component_index_ids() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(["IDX2", "IDX3"])
    repo = ReferenceDataRepository(db)

    index_ids = await repo.list_benchmark_component_index_ids_overlapping_window(
        benchmark_id="B1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        after_index_id="IDX1",
        limit=3,
    )

    assert index_ids == ["IDX2", "IDX3"]
    stmt = db.execute.await_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "SELECT DISTINCT benchmark_composition_series.index_id" in sql
    assert "benchmark_composition_series.benchmark_id = 'B1'" in sql
    assert "benchmark_composition_series.composition_effective_from <= '2026-01-31'" in sql
    assert "benchmark_composition_series.composition_effective_to >= '2026-01-01'" in sql
    assert "benchmark_composition_series.index_id > 'IDX1'" in sql
    assert "ORDER BY benchmark_composition_series.index_id ASC" in sql
    assert "LIMIT 3" in sql


@pytest.mark.asyncio
async def test_reference_data_repository_filters_window_components_by_index_ids() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult([])
    repo = ReferenceDataRepository(db)

    await repo.list_benchmark_components_overlapping_window(
        benchmark_id="B1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        index_ids=["IDX1", "IDX2"],
    )

    stmt = db.execute.await_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "benchmark_composition_series.index_id IN ('IDX1', 'IDX2')" in sql


@pytest.mark.asyncio
async def test_reference_data_repository_skips_empty_component_index_filter() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = ReferenceDataRepository(db)

    rows = await repo.list_benchmark_components_overlapping_window(
        benchmark_id="B1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        index_ids=[],
    )

    assert rows == []
    db.execute.assert_not_awaited()


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
async def test_benchmark_catalog_methods_return_latest_effective_row_per_business_key() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = [
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1",
                    effective_from=date(2025, 4, 1),
                    classification_labels={"strategy": "current"},
                ),
                SimpleNamespace(
                    benchmark_id="B2",
                    effective_from=date(2025, 1, 1),
                    classification_labels={"strategy": "other"},
                ),
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1",
                    index_id="IDX_1",
                    composition_effective_from=date(2025, 3, 1),
                    composition_weight=Decimal("0.55"),
                ),
                SimpleNamespace(
                    benchmark_id="B1",
                    index_id="IDX_2",
                    composition_effective_from=date(2025, 1, 1),
                    composition_weight=Decimal("0.40"),
                ),
            ]
        ),
    ]
    repo = ReferenceDataRepository(db)

    benchmarks = await repo.list_benchmark_definitions(date(2026, 4, 10))
    components = await repo.list_benchmark_components("B1", date(2026, 4, 10))

    assert [(row.benchmark_id, row.classification_labels) for row in benchmarks] == [
        ("B1", {"strategy": "current"}),
        ("B2", {"strategy": "other"}),
    ]
    assert [(row.index_id, row.composition_weight) for row in components] == [
        ("IDX_1", Decimal("0.55")),
        ("IDX_2", Decimal("0.40")),
    ]
    compiled_statements = [
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in db.execute.await_args_list
    ]
    assert (
        "row_number() OVER (PARTITION BY benchmark_definitions.benchmark_id"
        in compiled_statements[0]
    )
    assert (
        "row_number() OVER (PARTITION BY benchmark_composition_series.benchmark_id, "
        "benchmark_composition_series.index_id"
    ) in compiled_statements[1]
    for compiled in compiled_statements:
        assert "anon_1.rn = 1" in compiled


@pytest.mark.asyncio
async def test_benchmark_status_filter_is_normalized() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult([])
    repo = ReferenceDataRepository(db)

    await repo.list_benchmark_definitions(
        as_of_date=date(2026, 5, 3),
        benchmark_status=" Active ",
    )
    benchmark_sql = str(
        db.execute.await_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "benchmark_definitions.benchmark_status = 'active'" in benchmark_sql
    assert "lower(trim(benchmark_definitions.benchmark_status))" not in benchmark_sql


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
async def test_get_benchmark_coverage_evaluates_only_active_component_candidate_dates() -> None:
    repo = ReferenceDataRepository(AsyncMock(spec=AsyncSession))
    repo.list_benchmark_components_overlapping_window = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(
                index_id="IDX_A",
                composition_effective_from=date(2026, 1, 10),
                composition_effective_to=date(2026, 1, 12),
            )
        ]
    )
    repo.list_index_price_points = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(
                index_id="IDX_A",
                series_date=date(2026, 1, 5),
                quality_status="accepted",
            ),
            SimpleNamespace(
                index_id="IDX_A",
                series_date=date(2026, 1, 10),
                quality_status="accepted",
            ),
        ]
    )
    repo.list_benchmark_return_points = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(series_date=date(2026, 1, 5), quality_status="accepted"),
            SimpleNamespace(series_date=date(2026, 1, 10), quality_status="accepted"),
        ]
    )

    coverage = await repo.get_benchmark_coverage("B1", date(2026, 1, 1), date(2026, 1, 31))

    assert coverage["observed_dates"] == [date(2026, 1, 10)]
    assert coverage["observed_start_date"] == date(2026, 1, 10)
    assert coverage["observed_end_date"] == date(2026, 1, 10)


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
    compiled = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "row_number() OVER (PARTITION BY risk_free_series.series_date" in compiled
    assert "ORDER BY CASE WHEN (upper(trim(risk_free_series.quality_status)) = 'ACCEPTED')" in (
        compiled
    )
    assert "risk_free_series.source_timestamp DESC NULLS LAST" in compiled
    assert "risk_free_series.series_id DESC" in compiled
    assert "anon_1.rn = 1" in compiled


@pytest.mark.asyncio
async def test_market_reference_series_canonicalizes_duplicate_business_dates() -> None:
    db = AsyncMock(spec=AsyncSession)
    accepted_row = SimpleNamespace(
        index_id="IDX_A",
        benchmark_id="B1",
        series_date=date(2026, 1, 1),
        quality_status=" Accepted ",
        source_timestamp=None,
        series_id="front_office",
    )
    db.execute.side_effect = [
        _FakeExecuteResult([accepted_row]),
        _FakeExecuteResult([accepted_row]),
        _FakeExecuteResult([accepted_row]),
        _FakeExecuteResult([accepted_row]),
        _FakeExecuteResult([accepted_row]),
    ]

    repo = ReferenceDataRepository(db)

    index_prices = await repo.list_index_price_points(["IDX_A"], date(2026, 1, 1), date(2026, 1, 1))
    index_returns = await repo.list_index_return_points(
        ["IDX_A"], date(2026, 1, 1), date(2026, 1, 1)
    )
    benchmark_returns = await repo.list_benchmark_return_points(
        "B1", date(2026, 1, 1), date(2026, 1, 1)
    )
    index_price_series = await repo.list_index_price_series(
        "IDX_A", date(2026, 1, 1), date(2026, 1, 1)
    )
    index_return_series = await repo.list_index_return_series(
        "IDX_A", date(2026, 1, 1), date(2026, 1, 1)
    )

    result_sets = [
        index_prices,
        index_returns,
        benchmark_returns,
        index_price_series,
        index_return_series,
    ]
    assert all(len(rows) == 1 for rows in result_sets)
    assert all(rows[0].series_id == "front_office" for rows in result_sets)

    compiled_statements = [
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in db.execute.await_args_list
    ]
    assert "row_number() OVER (PARTITION BY index_price_series.index_id" in (compiled_statements[0])
    assert (
        "row_number() OVER (PARTITION BY index_return_series.index_id" in (compiled_statements[1])
    )
    assert (
        "row_number() OVER (PARTITION BY benchmark_return_series.benchmark_id"
        in (compiled_statements[2])
    )
    assert "row_number() OVER (PARTITION BY index_price_series.index_id" in (compiled_statements[3])
    assert (
        "row_number() OVER (PARTITION BY index_return_series.index_id" in (compiled_statements[4])
    )
    for compiled in compiled_statements:
        assert "upper(trim(" in compiled
        assert " = 'ACCEPTED'" in compiled
        assert "source_timestamp DESC NULLS LAST" in compiled
        assert "series_id DESC" in compiled
        assert "anon_1.rn = 1" in compiled


@pytest.mark.asyncio
async def test_get_risk_free_coverage_normalizes_quality_status_counts() -> None:
    repo = ReferenceDataRepository(AsyncMock(spec=AsyncSession))
    repo.list_risk_free_series = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(series_date=date(2026, 1, 1), quality_status=" Accepted "),
            SimpleNamespace(series_date=date(2026, 1, 2), quality_status="STALE"),
            SimpleNamespace(series_date=date(2026, 1, 3), quality_status=None),
        ]
    )

    coverage = await repo.get_risk_free_coverage("USD", date(2026, 1, 1), date(2026, 1, 3))

    assert coverage["quality_status_counts"] == {
        "accepted": 1,
        "stale": 1,
        "unknown": 1,
    }
