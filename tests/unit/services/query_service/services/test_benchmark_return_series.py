from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkReturnSeriesRequest,
    IntegrationWindow,
)
from src.services.query_service.app.services.benchmark_return_series import (
    build_benchmark_return_series_response,
)


def test_build_benchmark_return_series_response_maps_points_and_lineage() -> None:
    rows = [
        SimpleNamespace(
            series_date=date(2026, 1, 30),
            benchmark_return=Decimal("0.0019"),
            return_period="1d",
            return_convention="total_return_index",
            series_currency="USD",
            quality_status="accepted",
        )
    ]
    request = BenchmarkReturnSeriesRequest(
        as_of_date=date(2026, 1, 31),
        window=IntegrationWindow(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        ),
        frequency="daily",
    )

    response = build_benchmark_return_series_response(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        request=request,
        rows=rows,
    )

    assert response.benchmark_id == "BMK_GLOBAL_BALANCED_60_40"
    assert response.as_of_date == date(2026, 1, 31)
    assert response.resolved_window.start_date == date(2026, 1, 1)
    assert response.resolved_window.end_date == date(2026, 1, 31)
    assert response.frequency == "daily"
    assert response.request_fingerprint
    assert len(response.points) == 1
    assert response.points[0].series_date == date(2026, 1, 30)
    assert response.points[0].benchmark_return == Decimal("0.0019")
    assert response.points[0].return_period == "1d"
    assert response.points[0].return_convention == "total_return_index"
    assert response.points[0].series_currency == "USD"
    assert response.points[0].quality_status == "accepted"
    assert response.lineage == {
        "contract_version": "rfc_062_v1",
        "source_system": "lotus-core-query-service",
        "generated_by": "integration.benchmark_return_series",
    }
