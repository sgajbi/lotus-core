from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkMarketSeriesRequest,
)
from src.services.query_service.app.services.benchmark_market_series import (
    benchmark_market_series_fx_context,
    benchmark_market_series_normalization_status,
    build_benchmark_market_series_response,
)


def test_benchmark_market_series_fx_context_tracks_identity_and_missing_fx_request() -> None:
    identity_context = benchmark_market_series_fx_context(
        benchmark_currency="USD",
        target_currency="USD",
        requested_fields={"fx_rate"},
    )
    assert not identity_context.should_read_fx_rates
    assert (
        identity_context.initial_normalization_status
        == "native_component_series_with_identity_benchmark_to_target_fx_context"
    )

    missing_request_context = benchmark_market_series_fx_context(
        benchmark_currency="EUR",
        target_currency="USD",
        requested_fields={"index_price"},
    )
    assert not missing_request_context.should_read_fx_rates
    assert (
        missing_request_context.initial_normalization_status
        == "native_component_series_without_fx_context_request"
    )


def test_benchmark_market_series_normalization_status_reflects_fx_evidence() -> None:
    fx_context = benchmark_market_series_fx_context(
        benchmark_currency="EUR",
        target_currency="USD",
        requested_fields={"fx_rate"},
    )

    assert fx_context.should_read_fx_rates
    assert (
        benchmark_market_series_normalization_status(fx_context, {})
        == "native_component_series_with_missing_benchmark_to_target_fx_context"
    )
    assert (
        benchmark_market_series_normalization_status(
            fx_context,
            {date(2026, 1, 1): Decimal("1.1000")},
        )
        == "native_component_series_with_benchmark_to_target_fx_context"
    )


def test_build_benchmark_market_series_response_assembles_page_scoped_metadata() -> None:
    fx_context = benchmark_market_series_fx_context(
        benchmark_currency="EUR",
        target_currency="USD",
        requested_fields={"index_price", "component_weight", "fx_rate"},
    )

    response = build_benchmark_market_series_response(
        benchmark_id="BMK_GLOBAL_BALANCED",
        request=BenchmarkMarketSeriesRequest(
            as_of_date=date(2026, 1, 2),
            window={"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2)},
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price", "component_weight", "fx_rate"],
        ),
        benchmark_currency="EUR",
        request_scope_fingerprint="scope-123",
        page_size=1,
        has_more=True,
        next_page_token="token-2",
        index_ids=["IDX_A"],
        component_rows=[
            SimpleNamespace(
                index_id="IDX_A",
                composition_weight=Decimal("0.6000000000"),
                composition_effective_from=date(2026, 1, 1),
                composition_effective_to=None,
                quality_status="accepted",
                source_timestamp=datetime(2026, 1, 2, 8, 0, 0),
            )
        ],
        index_prices=[
            SimpleNamespace(
                index_id="IDX_A",
                series_date=date(2026, 1, 1),
                index_price=Decimal("100.0000000000"),
                series_currency="EUR",
                quality_status=" accepted ",
                source_timestamp=datetime(2026, 1, 2, 9, 0, 0),
            )
        ],
        index_returns=[],
        benchmark_returns=[],
        fx_rates={date(2026, 1, 1): Decimal("1.1000")},
        fx_context=fx_context,
    )

    assert response.product_name == "MarketDataWindow"
    assert response.request_fingerprint == "scope-123"
    assert response.page.next_page_token == "token-2"
    assert response.page.returned_component_count == 1
    assert response.component_series[0].index_id == "IDX_A"
    point = response.component_series[0].points[0]
    assert point.index_price == Decimal("100.0000000000")
    assert point.component_weight == Decimal("0.6000000000")
    assert point.fx_rate == Decimal("1.1000")
    assert response.quality_status_summary == {"accepted": 1}
    assert response.data_quality_status == "PARTIAL"
    assert response.latest_evidence_timestamp == datetime(2026, 1, 2, 9, 0, 0)
    assert (
        response.normalization_status
        == "native_component_series_with_benchmark_to_target_fx_context"
    )
