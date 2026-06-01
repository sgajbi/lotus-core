from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.services.index_catalog import (
    build_index_catalog_response,
)


def test_build_index_catalog_response_maps_index_definitions() -> None:
    row = SimpleNamespace(
        index_id="IDX_MSCI_WORLD_TR",
        index_name="MSCI World Total Return",
        index_currency="USD",
        index_type="equity_index",
        index_status="active",
        index_provider="MSCI",
        index_market="global_developed",
        classification_set_id="wm_global_taxonomy_v1",
        classification_labels={
            "asset_class": "equity",
            "sector": "broad_market_equity",
            "region": "global",
        },
        effective_from=date(2025, 1, 1),
        effective_to=None,
        quality_status="accepted",
        source_timestamp=datetime(2026, 1, 31, 8, 0, tzinfo=UTC),
        source_vendor="MSCI",
        source_record_id="idx_world_tr_v20260131",
    )

    response = build_index_catalog_response(
        as_of_date=date(2026, 1, 31),
        rows=[row],
    )

    assert response.as_of_date == date(2026, 1, 31)
    assert len(response.records) == 1
    record = response.records[0]
    assert record.index_id == "IDX_MSCI_WORLD_TR"
    assert record.index_name == "MSCI World Total Return"
    assert record.index_currency == "USD"
    assert record.index_type == "equity_index"
    assert record.index_status == "active"
    assert record.index_provider == "MSCI"
    assert record.index_market == "global_developed"
    assert record.classification_set_id == "wm_global_taxonomy_v1"
    assert record.classification_labels == {
        "asset_class": "equity",
        "sector": "broad_market_equity",
        "region": "global",
    }
    assert record.effective_from == date(2025, 1, 1)
    assert record.effective_to is None
    assert record.quality_status == "accepted"
    assert record.source_record_id == "idx_world_tr_v20260131"


def test_build_index_catalog_response_allows_empty_catalog() -> None:
    response = build_index_catalog_response(
        as_of_date=date(2026, 1, 31),
        rows=[],
    )

    assert response.as_of_date == date(2026, 1, 31)
    assert response.records == []
