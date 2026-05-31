from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.reference_data_mappers import (
    benchmark_definition_response,
    index_definition_response,
)


def test_benchmark_definition_response_maps_catalog_row_and_components() -> None:
    source_timestamp = datetime(2026, 1, 31, 8, tzinfo=UTC)

    response = benchmark_definition_response(
        SimpleNamespace(
            benchmark_id="BMK_GLOBAL_BALANCED_60_40",
            benchmark_name="Global Balanced 60/40",
            benchmark_type="composite",
            benchmark_currency="USD",
            return_convention="total_return_index",
            benchmark_status="active",
            benchmark_family="multi_asset",
            benchmark_provider="MSCI",
            rebalance_frequency="quarterly",
            classification_set_id="wm_global_taxonomy_v1",
            classification_labels={"asset_class": "multi_asset"},
            effective_from=date(2026, 1, 1),
            effective_to=None,
            quality_status="accepted",
            source_timestamp=source_timestamp,
            source_vendor="MSCI",
            source_record_id="bmk_60_40_v20260131",
        ),
        components=[
            SimpleNamespace(
                index_id="IDX_MSCI_WORLD_TR",
                composition_weight="0.6000000000",
                composition_effective_from=date(2026, 1, 1),
                composition_effective_to=None,
                rebalance_event_id="rebalance_2026q1",
            )
        ],
    )

    assert response.benchmark_id == "BMK_GLOBAL_BALANCED_60_40"
    assert response.classification_labels == {"asset_class": "multi_asset"}
    assert response.components[0].composition_weight == Decimal("0.6000000000")
    assert response.components[0].rebalance_event_id == "rebalance_2026q1"


def test_index_definition_response_maps_reference_catalog_row() -> None:
    source_timestamp = datetime(2026, 1, 31, 8, tzinfo=UTC)

    response = index_definition_response(
        SimpleNamespace(
            index_id="IDX_MSCI_WORLD_TR",
            index_name="MSCI World Total Return",
            index_currency="USD",
            index_type="equity_index",
            index_status="active",
            index_provider="MSCI",
            index_market="global_developed",
            classification_set_id="wm_global_taxonomy_v1",
            classification_labels={"asset_class": "equity", "region": "global"},
            effective_from=date(2026, 1, 1),
            effective_to=None,
            quality_status="accepted",
            source_timestamp=source_timestamp,
            source_vendor="MSCI",
            source_record_id="idx_world_tr_v20260131",
        )
    )

    assert response.index_id == "IDX_MSCI_WORLD_TR"
    assert response.index_provider == "MSCI"
    assert response.classification_labels == {"asset_class": "equity", "region": "global"}
