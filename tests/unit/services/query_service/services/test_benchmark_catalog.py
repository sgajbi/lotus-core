from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.benchmark_catalog import (
    build_benchmark_catalog_response,
)


def _benchmark_row(benchmark_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        benchmark_id=benchmark_id,
        benchmark_name="Global Balanced 60/40",
        benchmark_type="composite",
        benchmark_currency="USD",
        return_convention="total_return_index",
        benchmark_status="active",
        benchmark_family="multi_asset_strategic",
        benchmark_provider="MSCI",
        rebalance_frequency="quarterly",
        classification_set_id="wm_global_taxonomy_v1",
        classification_labels={"asset_class": "multi_asset", "region": "global"},
        effective_from=date(2025, 1, 1),
        effective_to=None,
        quality_status="accepted",
        source_timestamp=datetime(2026, 1, 31, 8, 0, tzinfo=UTC),
        source_vendor="MSCI",
        source_record_id=f"{benchmark_id}_20260131",
    )


def test_build_benchmark_catalog_response_maps_definitions_with_components() -> None:
    rows = [_benchmark_row("BMK_GLOBAL_BALANCED_60_40")]
    component = SimpleNamespace(
        index_id="IDX_MSCI_WORLD_TR",
        composition_weight=Decimal("0.60"),
        composition_effective_from=date(2025, 1, 1),
        composition_effective_to=None,
        rebalance_event_id="REB_2025_Q1",
    )

    response = build_benchmark_catalog_response(
        as_of_date=date(2026, 1, 31),
        rows=rows,
        components_by_benchmark={"BMK_GLOBAL_BALANCED_60_40": [component]},
    )

    assert response.as_of_date == date(2026, 1, 31)
    assert len(response.records) == 1
    record = response.records[0]
    assert record.benchmark_id == "BMK_GLOBAL_BALANCED_60_40"
    assert record.benchmark_name == "Global Balanced 60/40"
    assert record.benchmark_type == "composite"
    assert record.benchmark_currency == "USD"
    assert record.classification_labels == {
        "asset_class": "multi_asset",
        "region": "global",
    }
    assert len(record.components) == 1
    assert record.components[0].index_id == "IDX_MSCI_WORLD_TR"
    assert record.components[0].composition_weight == Decimal("0.60")


def test_build_benchmark_catalog_response_defaults_missing_component_scope() -> None:
    response = build_benchmark_catalog_response(
        as_of_date=date(2026, 1, 31),
        rows=[_benchmark_row("BMK_CASH_USD")],
        components_by_benchmark={},
    )

    assert response.records[0].benchmark_id == "BMK_CASH_USD"
    assert response.records[0].components == []
