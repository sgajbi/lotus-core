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
    assert await repo.list_index_definitions(date(2026, 1, 1), None, "USD", "equity", "active")
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
async def test_catalog_methods_return_latest_effective_row_per_business_key() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = [
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1",
                    effective_from=date(2025, 1, 1),
                    classification_labels={"strategy": "old"},
                ),
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
                    index_id="IDX_GLOBAL_EQUITY_TR",
                    effective_from=date(2025, 1, 6),
                    classification_labels={"asset_class": "equity"},
                ),
                SimpleNamespace(
                    index_id="IDX_GLOBAL_EQUITY_TR",
                    effective_from=date(2025, 4, 15),
                    classification_labels={
                        "asset_class": "equity",
                        "sector": "broad_market_equity",
                    },
                ),
                SimpleNamespace(
                    index_id="IDX_GLOBAL_BOND_TR",
                    effective_from=date(2025, 1, 6),
                    classification_labels={
                        "asset_class": "fixed_income",
                        "sector": "broad_market_fixed_income",
                    },
                ),
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    benchmark_id="B1",
                    index_id="IDX_1",
                    composition_effective_from=date(2025, 1, 1),
                    composition_weight=Decimal("0.60"),
                ),
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
    indices = await repo.list_index_definitions(date(2026, 4, 10))
    components = await repo.list_benchmark_components("B1", date(2026, 4, 10))

    assert [(row.benchmark_id, row.classification_labels) for row in benchmarks] == [
        ("B1", {"strategy": "current"}),
        ("B2", {"strategy": "other"}),
    ]
    assert [(row.index_id, row.classification_labels) for row in indices] == [
        (
            "IDX_GLOBAL_BOND_TR",
            {"asset_class": "fixed_income", "sector": "broad_market_fixed_income"},
        ),
        ("IDX_GLOBAL_EQUITY_TR", {"asset_class": "equity", "sector": "broad_market_equity"}),
    ]
    assert [(row.index_id, row.composition_weight) for row in components] == [
        ("IDX_1", Decimal("0.55")),
        ("IDX_2", Decimal("0.40")),
    ]


@pytest.mark.asyncio
async def test_resolve_model_portfolio_definition_uses_approved_effective_model() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(
        [SimpleNamespace(model_portfolio_id="MODEL_SG_BALANCED_DPM")]
    )
    repo = ReferenceDataRepository(db)

    row = await repo.resolve_model_portfolio_definition(
        "MODEL_SG_BALANCED_DPM",
        date(2026, 3, 31),
    )

    assert row.model_portfolio_id == "MODEL_SG_BALANCED_DPM"
    compiled = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "model_portfolio_definitions.model_portfolio_id = 'MODEL_SG_BALANCED_DPM'" in compiled
    assert "model_portfolio_definitions.approval_status = 'approved'" in compiled
    assert "model_portfolio_definitions.effective_from <= '2026-03-31'" in compiled


@pytest.mark.asyncio
async def test_list_model_portfolio_targets_returns_latest_active_targets_by_default() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(
        [
            SimpleNamespace(
                model_portfolio_id="MODEL_SG_BALANCED_DPM",
                model_portfolio_version="2026.03",
                instrument_id="EQ_US_AAPL",
                effective_from=date(2026, 3, 25),
                target_weight=Decimal("0.55"),
            ),
            SimpleNamespace(
                model_portfolio_id="MODEL_SG_BALANCED_DPM",
                model_portfolio_version="2026.03",
                instrument_id="EQ_US_AAPL",
                effective_from=date(2026, 4, 1),
                target_weight=Decimal("0.60"),
            ),
            SimpleNamespace(
                model_portfolio_id="MODEL_SG_BALANCED_DPM",
                model_portfolio_version="2026.03",
                instrument_id="FI_US_TREASURY_10Y",
                effective_from=date(2026, 3, 25),
                target_weight=Decimal("0.40"),
            ),
        ]
    )
    repo = ReferenceDataRepository(db)

    rows = await repo.list_model_portfolio_targets(
        model_portfolio_id="MODEL_SG_BALANCED_DPM",
        model_portfolio_version="2026.03",
        as_of_date=date(2026, 4, 30),
    )

    assert [(row.instrument_id, row.target_weight) for row in rows] == [
        ("EQ_US_AAPL", Decimal("0.60")),
        ("FI_US_TREASURY_10Y", Decimal("0.40")),
    ]
    compiled = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "model_portfolio_targets.target_status = 'active'" in compiled


@pytest.mark.asyncio
async def test_list_model_portfolio_targets_can_include_inactive_targets() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult([])
    repo = ReferenceDataRepository(db)

    await repo.list_model_portfolio_targets(
        model_portfolio_id="MODEL_SG_BALANCED_DPM",
        model_portfolio_version="2026.03",
        as_of_date=date(2026, 4, 30),
        include_inactive_targets=True,
    )

    compiled = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "model_portfolio_targets.target_status =" not in compiled


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


@pytest.mark.asyncio
async def test_list_index_definitions_filters_targeted_index_ids() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(
        [
            SimpleNamespace(
                index_id="IDX_KEEP",
                effective_from=date(2026, 1, 1),
                classification_labels={"asset_class": "equity"},
            ),
            SimpleNamespace(
                index_id="IDX_SKIP",
                effective_from=date(2026, 1, 1),
                classification_labels={"asset_class": "fixed_income"},
            ),
        ]
    )
    repo = ReferenceDataRepository(db)

    rows = await repo.list_index_definitions(date(2026, 1, 31), ["IDX_KEEP"])

    assert [row.index_id for row in rows] == ["IDX_KEEP", "IDX_SKIP"]
    compiled = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "index_definitions.index_id IN ('IDX_KEEP')" in compiled
