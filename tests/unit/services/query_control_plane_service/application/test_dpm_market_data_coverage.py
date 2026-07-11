"""Application policy tests for DPM market-data coverage."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.dpm_source_readiness import (
    market_data_coverage,
)
from src.services.query_control_plane_service.app.contracts.market_data_coverage import (
    MarketDataCoverageRequest,
    MarketDataCurrencyPair,
)
from src.services.query_control_plane_service.app.domain.dpm_source_readiness import (
    FxRateEvidence,
    MarketPriceEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)


def _price(*, price_date: date = date(2026, 4, 10)) -> MarketPriceEvidence:
    return MarketPriceEvidence(
        security_id="EQ_US_AAPL",
        price_date=price_date,
        price=Decimal("187.1200000000"),
        currency="USD",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def _fx(*, rate_date: date = date(2026, 4, 10)) -> FxRateEvidence:
    return FxRateEvidence(
        from_currency="USD",
        to_currency="SGD",
        rate_date=rate_date,
        rate=Decimal("1.3521000000"),
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def _request() -> MarketDataCoverageRequest:
    return MarketDataCoverageRequest(
        as_of_date=date(2026, 4, 10),
        instrument_ids=["EQ_US_AAPL"],
        currency_pairs=[MarketDataCurrencyPair(from_currency="USD", to_currency="SGD")],
        valuation_currency="sgd",
        max_staleness_days=5,
        tenant_id="tenant-1",
    )


def _build(
    *,
    prices: list[MarketPriceEvidence],
    fx_rates: list[FxRateEvidence],
):
    request = _request()
    return market_data_coverage.build_market_data_coverage_response(
        request=request,
        scope=market_data_coverage.market_data_coverage_scope(request),
        prices=prices,
        fx_rates=fx_rates,
        generated_at=GENERATED_AT,
    )


def test_complete_market_data_is_ready_current_and_hashed() -> None:
    response = _build(prices=[_price()], fx_rates=[_fx()])

    assert response.valuation_currency == "SGD"
    assert response.supportability.state == "READY"
    assert response.data_quality_status == "COMPLETE"
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.source_batch_fingerprint == response.content_hash == response.source_digest
    assert response.latest_evidence_timestamp == EVIDENCE_AT


@pytest.mark.parametrize(
    ("prices", "fx_rates", "state", "reason"),
    [
        ([_price(price_date=date(2026, 4, 1))], [_fx()], "DEGRADED", "MARKET_DATA_STALE"),
        ([], [_fx()], "INCOMPLETE", "MARKET_DATA_MISSING"),
        ([_price()], [], "INCOMPLETE", "MARKET_DATA_MISSING"),
        ([_price()], [_fx(rate_date=date(2026, 4, 1))], "DEGRADED", "MARKET_DATA_STALE"),
    ],
)
def test_market_data_classifies_stale_and_missing_evidence(
    prices: list[MarketPriceEvidence],
    fx_rates: list[FxRateEvidence],
    state: str,
    reason: str,
) -> None:
    response = _build(prices=prices, fx_rates=fx_rates)

    assert response.supportability.state == state
    assert response.supportability.reason == reason
    assert response.data_quality_status == "PARTIAL"


def test_market_data_hash_excludes_generation_time() -> None:
    request = _request()
    scope = market_data_coverage.market_data_coverage_scope(request)
    first = market_data_coverage.build_market_data_coverage_response(
        request=request,
        scope=scope,
        prices=[_price()],
        fx_rates=[_fx()],
        generated_at=GENERATED_AT,
    )
    second = market_data_coverage.build_market_data_coverage_response(
        request=request,
        scope=scope,
        prices=[_price()],
        fx_rates=[_fx()],
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.content_hash == second.content_hash


@pytest.mark.asyncio
async def test_service_reads_each_deduplicated_source_scope_once() -> None:
    class Reader:
        async def list_latest_market_prices(self, **kwargs: object):
            self.price_scope = kwargs
            return [_price()]

        async def list_latest_fx_rates(self, **kwargs: object):
            self.fx_scope = kwargs
            return [_fx()]

    reader = Reader()
    response = await market_data_coverage.MarketDataCoverageService(
        reader=reader,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).resolve(_request())

    assert response.supportability.state == "READY"
    assert reader.price_scope["security_ids"] == ["EQ_US_AAPL"]
    assert reader.fx_scope["currency_pairs"] == [("USD", "SGD")]
