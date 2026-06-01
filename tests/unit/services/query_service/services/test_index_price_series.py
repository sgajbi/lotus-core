from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    IndexSeriesRequest,
    IntegrationWindow,
)
from src.services.query_service.app.services.index_price_series import (
    build_index_price_series_response,
)


def test_build_index_price_series_response_maps_points_and_runtime_metadata() -> None:
    observed_at = datetime(2026, 1, 31, 9, 30, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            series_date=date(2026, 1, 30),
            index_price=Decimal("4567.1234"),
            series_currency="USD",
            value_convention="close_price",
            quality_status="accepted",
            observed_at=observed_at,
        )
    ]
    request = IndexSeriesRequest(
        as_of_date=date(2026, 1, 31),
        window=IntegrationWindow(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        ),
        frequency="daily",
    )

    response = build_index_price_series_response(
        index_id="IDX_MSCI_WORLD_TR",
        request=request,
        rows=rows,
    )

    assert response.product_name == "IndexSeriesWindow"
    assert response.index_id == "IDX_MSCI_WORLD_TR"
    assert response.as_of_date == date(2026, 1, 31)
    assert response.resolved_window.start_date == date(2026, 1, 1)
    assert response.resolved_window.end_date == date(2026, 1, 31)
    assert response.frequency == "daily"
    assert len(response.points) == 1
    assert response.points[0].series_date == date(2026, 1, 30)
    assert response.points[0].index_price == Decimal("4567.1234")
    assert response.points[0].series_currency == "USD"
    assert response.points[0].value_convention == "close_price"
    assert response.points[0].quality_status == "accepted"
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == observed_at
    assert response.lineage == {
        "contract_version": "rfc_062_v1",
        "source_system": "lotus-core-query-service",
        "generated_by": "integration.index_price_series",
    }
