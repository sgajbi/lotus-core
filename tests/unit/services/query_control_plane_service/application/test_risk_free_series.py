"""Application tests for governed risk-free series windows."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.risk_free_series import (
    RiskFreeSeriesService,
    build_risk_free_series_response,
)
from src.services.query_control_plane_service.app.contracts.risk_free_series import (
    IntegrationWindow,
    RiskFreeSeriesRequest,
)
from src.services.query_control_plane_service.app.domain.risk_free_series import (
    RiskFreeRateEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)
REQUEST = RiskFreeSeriesRequest(
    currency="usd",
    as_of_date=date(2026, 4, 10),
    series_mode="annualized_rate_series",
    window=IntegrationWindow(start_date=date(2026, 4, 9), end_date=date(2026, 4, 10)),
    frequency="daily",
)


def _rate(series_date: date, *, quality_status: str = "accepted") -> RiskFreeRateEvidence:
    return RiskFreeRateEvidence(
        series_id="official-overnight-rate",
        risk_free_curve_id="USD_SOFR",
        series_date=series_date,
        value=Decimal("0.035"),
        value_convention="annualized_rate",
        day_count_convention="act_360",
        compounding_convention="simple",
        series_currency="USD",
        quality_status=quality_status,
        observed_at=EVIDENCE_AT,
        source_vendor="Federal Reserve Bank of New York",
        source_record_id=f"sofr:{series_date.isoformat()}",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def test_complete_window_is_current_and_hash_is_deterministic() -> None:
    rows = [_rate(date(2026, 4, 9)), _rate(date(2026, 4, 10))]
    first = build_risk_free_series_response(
        currency="USD", request=REQUEST, rows=rows, generated_at=GENERATED_AT
    )
    second = build_risk_free_series_response(
        currency="USD",
        request=REQUEST,
        rows=rows,
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.completeness_status == "COMPLETE"
    assert first.source_evidence_current is True
    assert first.source_batch_fingerprint == first.content_hash == first.source_digest
    assert first.content_hash == second.content_hash
    assert first.points[0].day_count_convention == "act_360"


def test_stale_partial_window_is_not_current() -> None:
    response = build_risk_free_series_response(
        currency="USD",
        request=REQUEST,
        rows=[_rate(date(2026, 4, 10), quality_status="stale")],
        generated_at=GENERATED_AT,
    )
    assert response.completeness_status == "PARTIAL"
    assert response.source_evidence_current is False


@pytest.mark.asyncio
async def test_service_normalizes_currency_and_passes_window() -> None:
    class Reader:
        async def list_rates(self, **kwargs: object) -> list[RiskFreeRateEvidence]:
            self.kwargs = kwargs
            return [_rate(date(2026, 4, 9)), _rate(date(2026, 4, 10))]

    reader = Reader()
    response = await RiskFreeSeriesService(
        reader=reader,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).get(request=REQUEST)

    assert response.currency == "USD"
    assert reader.kwargs == {
        "currency": "USD",
        "start_date": date(2026, 4, 9),
        "end_date": date(2026, 4, 10),
    }
