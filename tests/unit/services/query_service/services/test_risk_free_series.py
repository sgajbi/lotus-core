from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    IntegrationWindow,
    RiskFreeSeriesRequest,
)
from src.services.query_service.app.services.risk_free_series import (
    build_risk_free_series_response,
)


def test_build_risk_free_series_response_maps_points_and_runtime_metadata() -> None:
    observed_at = datetime(2026, 1, 31, 9, 30, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            series_date=date(2026, 1, 30),
            value=Decimal("0.0350"),
            value_convention="annualized_rate",
            day_count_convention="act_360",
            compounding_convention="simple",
            series_currency="USD",
            quality_status="accepted",
            observed_at=observed_at,
        )
    ]
    request = RiskFreeSeriesRequest(
        currency="usd",
        as_of_date=date(2026, 1, 31),
        series_mode="annualized_rate_series",
        window=IntegrationWindow(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        ),
        frequency="daily",
    )

    response = build_risk_free_series_response(
        currency="USD",
        request=request,
        rows=rows,
    )

    assert response.product_name == "RiskFreeSeriesWindow"
    assert response.currency == "USD"
    assert response.as_of_date == date(2026, 1, 31)
    assert response.series_mode == "annualized_rate_series"
    assert response.resolved_window.start_date == date(2026, 1, 1)
    assert response.resolved_window.end_date == date(2026, 1, 31)
    assert response.frequency == "daily"
    assert response.request_fingerprint
    assert len(response.points) == 1
    assert response.points[0].series_date == date(2026, 1, 30)
    assert response.points[0].value == Decimal("0.0350")
    assert response.points[0].value_convention == "annualized_rate"
    assert response.points[0].day_count_convention == "act_360"
    assert response.points[0].compounding_convention == "simple"
    assert response.points[0].series_currency == "USD"
    assert response.points[0].quality_status == "accepted"
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == observed_at
    assert response.lineage == {
        "contract_version": "rfc_062_v1",
        "source_system": "lotus-core-query-service",
        "generated_by": "integration.risk_free_series",
    }
