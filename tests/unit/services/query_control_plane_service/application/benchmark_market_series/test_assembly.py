"""Tests for benchmark market-series response assembly and source proof."""

from datetime import UTC, date, datetime
from decimal import Decimal

from portfolio_common.reference_data_paging import ReferencePageRequest

from services.query_control_plane_service.app.application.benchmark_market_series.assembly import (
    build_benchmark_market_series_response,
)
from services.query_control_plane_service.app.application.benchmark_market_series.policy import (
    resolve_fx_context,
)
from services.query_control_plane_service.app.contracts.benchmark_market_series import (
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
)
from services.query_control_plane_service.app.contracts.common import IntegrationWindow
from services.query_control_plane_service.app.domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)
from services.query_control_plane_service.app.domain.index_series import IndexPriceEvidence
from services.query_control_plane_service.app.domain.market_fx import FxRateEvidence

OBSERVED_AT = datetime(2026, 1, 31, 8, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 1, 31, 9, 0, tzinfo=UTC)


def _request(*, target_currency: str = "SGD", page_size: int = 2) -> BenchmarkMarketSeriesRequest:
    return BenchmarkMarketSeriesRequest(
        as_of_date=date(2026, 1, 31),
        window=IntegrationWindow(start_date=date(2026, 1, 30), end_date=date(2026, 1, 31)),
        frequency="daily",
        target_currency=target_currency,
        series_fields=["index_price", "component_weight", "fx_rate"],
        page=ReferencePageRequest(page_size=page_size),
    )


def _definition() -> BenchmarkDefinitionEvidence:
    return BenchmarkDefinitionEvidence(
        benchmark_id="BMK_1",
        benchmark_name="Global Balanced",
        benchmark_type="COMPOSITE",
        benchmark_currency="USD",
        return_convention="TOTAL_RETURN",
        benchmark_status="ACTIVE",
        benchmark_family=None,
        benchmark_provider="PROVIDER",
        rebalance_frequency="MONTHLY",
        classification_set_id=None,
        classification_labels={},
        effective_from=date(2020, 1, 1),
        effective_to=None,
        source_timestamp=OBSERVED_AT,
        source_vendor="PROVIDER",
        source_record_id="BMK_1",
        quality_status="ACCEPTED",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )


def _component(*, index_id: str = "IDX_1") -> BenchmarkComponentEvidence:
    return BenchmarkComponentEvidence(
        benchmark_id="BMK_1",
        index_id=index_id,
        composition_effective_from=date(2026, 1, 1),
        composition_effective_to=None,
        composition_weight=Decimal("1.0000000000"),
        rebalance_event_id="REB_1",
        source_timestamp=OBSERVED_AT,
        source_vendor="PROVIDER",
        source_record_id=f"BMK_1:{index_id}",
        quality_status="ACCEPTED",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )


def _price(*, index_id: str = "IDX_1") -> IndexPriceEvidence:
    return IndexPriceEvidence(
        series_id=f"PRICE:{index_id}",
        index_id=index_id,
        series_date=date(2026, 1, 30),
        index_price=Decimal("100.2500000000"),
        series_currency="USD",
        value_convention="CLOSE",
        quality_status="ACCEPTED",
        observed_at=OBSERVED_AT,
        source_vendor="PROVIDER",
        source_record_id=f"PRICE:{index_id}",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )


def _fx() -> FxRateEvidence:
    return FxRateEvidence(
        from_currency="USD",
        to_currency="SGD",
        rate_date=date(2026, 1, 30),
        rate=Decimal("1.3500000000"),
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )


def _response(
    *,
    request: BenchmarkMarketSeriesRequest | None = None,
    has_more: bool = False,
    index_ids: tuple[str, ...] = ("IDX_1",),
    components: list[BenchmarkComponentEvidence] | None = None,
    prices: list[IndexPriceEvidence] | None = None,
    fx_rates: list[FxRateEvidence] | None = None,
    generated_at: datetime = GENERATED_AT,
) -> BenchmarkMarketSeriesResponse:
    resolved_request = request or _request()
    context = resolve_fx_context(
        benchmark_currency="USD",
        target_currency=resolved_request.target_currency,
        requested_fields=frozenset(resolved_request.series_fields),
    )
    return build_benchmark_market_series_response(
        benchmark_id="BMK_1",
        request=resolved_request,
        definition=_definition(),
        request_fingerprint="request-1",
        page_size=resolved_request.page.page_size,
        has_more=has_more,
        next_page_token="next" if has_more else None,
        index_ids=index_ids,
        components=components if components is not None else [_component()],
        index_prices=prices if prices is not None else [_price()],
        index_returns=[],
        benchmark_returns=[],
        fx_rates=fx_rates if fx_rates is not None else [_fx()],
        fx_context=context,
        generated_at=generated_at,
    )


def test_response_exposes_current_deterministic_source_proof() -> None:
    response = _response()

    assert response.data_quality_status == "COMPLETE"
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.generated_at == GENERATED_AT
    assert response.content_hash.startswith("sha256:")
    assert response.source_digest == response.content_hash
    assert response.source_batch_fingerprint == response.content_hash
    assert response.source_lineage["source_product"] == "MarketDataWindow"
    assert any("IndexSeriesWindow/IDX_1" in ref for ref in response.source_refs)
    assert response.page.request_scope_fingerprint == "request-1"


def test_content_hash_excludes_generation_time_and_input_order() -> None:
    second_component = _component(index_id="IDX_2")
    second_price = _price(index_id="IDX_2")
    first = _response(
        index_ids=("IDX_1", "IDX_2"),
        components=[_component(), second_component],
        prices=[_price(), second_price],
    )
    second = _response(
        index_ids=("IDX_1", "IDX_2"),
        components=[second_component, _component()],
        prices=[second_price, _price()],
        generated_at=datetime(2026, 1, 31, 10, 0, tzinfo=UTC),
    )

    assert first.content_hash == second.content_hash


def test_non_terminal_page_is_truthfully_partial() -> None:
    response = _response(has_more=True)

    assert response.data_quality_status == "PARTIAL"
    assert response.source_evidence_current is False
    assert response.freshness_status == "PARTIAL"
    assert response.page.next_page_token == "next"


def test_missing_requested_fx_evidence_is_partial() -> None:
    response = _response(fx_rates=[])

    assert response.data_quality_status == "PARTIAL"
    assert response.source_evidence_current is False
    assert (
        response.normalization_status
        == "native_component_series_with_missing_benchmark_to_target_fx_context"
    )


def test_identity_fx_is_one_without_external_source_read() -> None:
    response = _response(request=_request(target_currency="USD"), fx_rates=[])

    assert response.data_quality_status == "COMPLETE"
    assert response.component_series[0].points[0].fx_rate == Decimal("1.0000000000")
    assert (
        response.normalization_status
        == "native_component_series_with_identity_benchmark_to_target_fx_context"
    )


def test_component_weight_only_request_emits_effective_segment_point() -> None:
    request = _request()
    request.series_fields = ["component_weight"]
    response = _response(request=request, prices=[], fx_rates=[])

    assert response.component_series[0].points[0].series_date == request.window.start_date
    assert response.component_series[0].points[0].component_weight == Decimal("1.0000000000")
    assert response.quality_status_summary == {"accepted": 1}


def test_empty_component_page_is_unavailable() -> None:
    response = _response(index_ids=(), components=[], prices=[], fx_rates=[])

    assert response.data_quality_status == "EMPTY"
    assert response.freshness_status == "UNAVAILABLE"
    assert response.component_series == []
