"""Tests for QCP-owned benchmark and risk-free coverage diagnostics."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest

from services.query_control_plane_service.app.application.reference_coverage import (
    ReferenceCoverageService,
)
from services.query_control_plane_service.app.contracts.common import IntegrationWindow
from services.query_control_plane_service.app.contracts.reference_coverage import CoverageRequest
from services.query_control_plane_service.app.domain.benchmark_definition import (
    BenchmarkComponentEvidence,
)
from services.query_control_plane_service.app.domain.benchmark_return_series import (
    BenchmarkReturnEvidence,
)
from services.query_control_plane_service.app.domain.index_series import IndexPriceEvidence
from services.query_control_plane_service.app.domain.risk_free_series import RiskFreeRateEvidence
from services.query_control_plane_service.app.ports.benchmark_definition import (
    BenchmarkDefinitionReader,
)
from services.query_control_plane_service.app.ports.benchmark_return_series import (
    BenchmarkReturnSeriesReader,
)
from services.query_control_plane_service.app.ports.index_series import IndexSeriesReader
from services.query_control_plane_service.app.ports.risk_free_series import RiskFreeSeriesReader

OBSERVED_AT = datetime(2026, 1, 2, 8, tzinfo=UTC)
GENERATED_AT = datetime(2026, 1, 2, 9, tzinfo=UTC)


class BenchmarkReader:
    async def list_components_overlapping_window(
        self, **_: object
    ) -> list[BenchmarkComponentEvidence]:
        return [_component("IDX_1"), _component("IDX_2")]


class IndexReader:
    def __init__(self, rows: list[IndexPriceEvidence]):
        self.rows = rows

    async def list_prices_for_indices(self, **_: object) -> list[IndexPriceEvidence]:
        return self.rows


class BenchmarkReturnReader:
    async def list_returns(self, **_: object) -> list[BenchmarkReturnEvidence]:
        return [_benchmark_return(date(2026, 1, 1)), _benchmark_return(date(2026, 1, 2))]


class RiskFreeReader:
    def __init__(self, rows: list[RiskFreeRateEvidence]):
        self.rows = rows
        self.currency: str | None = None

    async def list_rates(self, *, currency: str, **_: object) -> list[RiskFreeRateEvidence]:
        self.currency = currency
        return self.rows


def _service(
    *,
    prices: list[IndexPriceEvidence] | None = None,
    risk_free: list[RiskFreeRateEvidence] | None = None,
    generated_at: datetime = GENERATED_AT,
) -> tuple[ReferenceCoverageService, RiskFreeReader]:
    risk_free_reader = RiskFreeReader(risk_free or [])
    return (
        ReferenceCoverageService(
            benchmark_reader=cast(BenchmarkDefinitionReader, BenchmarkReader()),
            index_series_reader=cast(
                IndexSeriesReader,
                IndexReader(
                    prices
                    if prices is not None
                    else [
                        _price("IDX_1", date(2026, 1, 1)),
                        _price("IDX_2", date(2026, 1, 1)),
                        _price("IDX_1", date(2026, 1, 2)),
                    ]
                ),
            ),
            benchmark_return_reader=cast(BenchmarkReturnSeriesReader, BenchmarkReturnReader()),
            risk_free_reader=cast(RiskFreeSeriesReader, risk_free_reader),
            clock=lambda: generated_at,
        ),
        risk_free_reader,
    )


def _request() -> CoverageRequest:
    return CoverageRequest(
        window=IntegrationWindow(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    )


@pytest.mark.asyncio
async def test_benchmark_coverage_requires_every_active_component_price() -> None:
    service, _ = _service()

    response = await service.get_benchmark(benchmark_id="BMK_1", request=_request())

    assert response.observed_start_date == date(2026, 1, 1)
    assert response.observed_end_date == date(2026, 1, 1)
    assert response.missing_dates_count == 1
    assert response.missing_dates_sample == [date(2026, 1, 2)]
    assert response.total_points == 5
    assert response.data_quality_status == "PARTIAL"


@pytest.mark.asyncio
async def test_complete_benchmark_coverage_exposes_deterministic_source_proof() -> None:
    prices = [
        _price(index_id, series_date)
        for series_date in (date(2026, 1, 1), date(2026, 1, 2))
        for index_id in ("IDX_1", "IDX_2")
    ]
    first, _ = _service(prices=prices)
    second, _ = _service(
        prices=list(reversed(prices)),
        generated_at=datetime(2026, 1, 2, 10, tzinfo=UTC),
    )

    first_response = await first.get_benchmark(benchmark_id="BMK_1", request=_request())
    second_response = await second.get_benchmark(benchmark_id="BMK_1", request=_request())

    assert first_response.data_quality_status == "COMPLETE"
    assert first_response.source_evidence_current is True
    assert first_response.freshness_status == "CURRENT"
    assert first_response.source_batch_fingerprint == first_response.content_hash
    assert first_response.source_digest == first_response.content_hash
    assert first_response.content_hash == second_response.content_hash
    assert first_response.generated_at != second_response.generated_at


@pytest.mark.asyncio
async def test_risk_free_coverage_normalizes_currency_and_reports_empty_source() -> None:
    service, reader = _service()

    response = await service.get_risk_free(currency=" usd ", request=_request())

    assert reader.currency == "USD"
    assert response.total_points == 0
    assert response.data_quality_status == "UNRECONCILED"
    assert response.freshness_status == "UNAVAILABLE"
    assert response.source_evidence_current is False


@pytest.mark.asyncio
async def test_risk_free_coverage_propagates_stale_quality() -> None:
    rows = [
        replace(_risk_free(date(2026, 1, 1)), quality_status="STALE"),
        _risk_free(date(2026, 1, 2)),
    ]
    service, _ = _service(risk_free=rows)

    response = await service.get_risk_free(currency="USD", request=_request())

    assert response.data_quality_status == "STALE"
    assert response.quality_status_distribution == {"accepted": 1, "stale": 1}
    assert response.source_evidence_current is False


def _component(index_id: str) -> BenchmarkComponentEvidence:
    return BenchmarkComponentEvidence(
        benchmark_id="BMK_1",
        index_id=index_id,
        composition_effective_from=date(2026, 1, 1),
        composition_effective_to=None,
        composition_weight=Decimal("0.5000000000"),
        rebalance_event_id="REB_1",
        source_timestamp=OBSERVED_AT,
        source_vendor="PROVIDER",
        source_record_id=f"BMK_1:{index_id}",
        quality_status="ACCEPTED",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )


def _price(index_id: str, series_date: date) -> IndexPriceEvidence:
    return IndexPriceEvidence(
        series_id=f"PRICE:{index_id}:{series_date}",
        index_id=index_id,
        series_date=series_date,
        index_price=Decimal("100.0000000000"),
        series_currency="USD",
        value_convention="CLOSE",
        quality_status="ACCEPTED",
        observed_at=OBSERVED_AT,
        source_vendor="PROVIDER",
        source_record_id=f"PRICE:{index_id}:{series_date}",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )


def _benchmark_return(series_date: date) -> BenchmarkReturnEvidence:
    return BenchmarkReturnEvidence(
        series_id=f"RETURN:BMK_1:{series_date}",
        benchmark_id="BMK_1",
        series_date=series_date,
        benchmark_return=Decimal("0.0010000000"),
        return_period="DAILY",
        return_convention="TOTAL_RETURN",
        series_currency="USD",
        quality_status="ACCEPTED",
        observed_at=OBSERVED_AT,
        source_vendor="PROVIDER",
        source_record_id=f"RETURN:BMK_1:{series_date}",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )


def _risk_free(series_date: date) -> RiskFreeRateEvidence:
    return RiskFreeRateEvidence(
        series_id=f"RF:USD:{series_date}",
        risk_free_curve_id="RF_USD",
        series_date=series_date,
        value=Decimal("0.0300000000"),
        value_convention="ANNUALIZED_RATE",
        day_count_convention="ACT_360",
        compounding_convention="SIMPLE",
        series_currency="USD",
        quality_status="ACCEPTED",
        observed_at=OBSERVED_AT,
        source_vendor="PROVIDER",
        source_record_id=f"RF:USD:{series_date}",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )
