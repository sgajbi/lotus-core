import asyncio
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkMarketSeriesRequest,
)
from src.services.query_service.app.services.benchmark_market_series import (
    benchmark_market_series_currency,
    benchmark_market_series_evidence_plan,
    benchmark_market_series_evidence_read_names,
    benchmark_market_series_fx_context,
    benchmark_market_series_index_page,
    benchmark_market_series_next_page_token_payload,
    benchmark_market_series_normalization_status,
    benchmark_market_series_page_token,
    benchmark_market_series_read_evidence,
    benchmark_market_series_request_scope,
    build_benchmark_market_series_response,
)


def test_benchmark_market_series_currency_prefers_benchmark_definition() -> None:
    assert (
        benchmark_market_series_currency(
            definition=SimpleNamespace(benchmark_currency="EUR"),
            target_currency="USD",
        )
        == "EUR"
    )


def test_benchmark_market_series_currency_falls_back_to_target_or_unknown() -> None:
    assert benchmark_market_series_currency(definition=None, target_currency="USD") == "USD"
    assert benchmark_market_series_currency(definition=None, target_currency=None) == "UNKNOWN"


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


def test_benchmark_market_series_evidence_plan_tracks_requested_market_families() -> None:
    fx_context = benchmark_market_series_fx_context(
        benchmark_currency="EUR",
        target_currency="USD",
        requested_fields={"index_price", "benchmark_return", "fx_rate"},
    )

    plan = benchmark_market_series_evidence_plan(
        requested_fields={"index_price", "benchmark_return", "fx_rate"},
        fx_context=fx_context,
    )

    assert plan.include_index_prices
    assert not plan.include_index_returns
    assert plan.include_benchmark_returns
    assert plan.include_fx_rates


def test_benchmark_market_series_evidence_plan_suppresses_identity_fx_read() -> None:
    fx_context = benchmark_market_series_fx_context(
        benchmark_currency="USD",
        target_currency="USD",
        requested_fields={"index_return", "fx_rate"},
    )

    plan = benchmark_market_series_evidence_plan(
        requested_fields={"index_return", "fx_rate"},
        fx_context=fx_context,
    )

    assert not plan.include_index_prices
    assert plan.include_index_returns
    assert not plan.include_benchmark_returns
    assert not plan.include_fx_rates


def test_benchmark_market_series_evidence_read_names_preserve_repository_order() -> None:
    fx_context = benchmark_market_series_fx_context(
        benchmark_currency="EUR",
        target_currency="USD",
        requested_fields={"benchmark_return", "index_price", "index_return", "fx_rate"},
    )
    plan = benchmark_market_series_evidence_plan(
        requested_fields={"benchmark_return", "index_price", "index_return", "fx_rate"},
        fx_context=fx_context,
    )

    assert benchmark_market_series_evidence_read_names(plan) == [
        "components",
        "index_prices",
        "index_returns",
        "benchmark_returns",
        "fx_rates",
    ]


def test_benchmark_market_series_read_evidence_collects_only_planned_families() -> None:
    async def run_case() -> tuple[dict[str, str], list[str]]:
        read_order: list[str] = []

        async def read_family(name: str) -> str:
            read_order.append(name)
            return f"{name}-rows"

        fx_context = benchmark_market_series_fx_context(
            benchmark_currency="USD",
            target_currency="USD",
            requested_fields={"index_price", "fx_rate"},
        )
        plan = benchmark_market_series_evidence_plan(
            requested_fields={"index_price", "fx_rate"},
            fx_context=fx_context,
        )
        results = await benchmark_market_series_read_evidence(
            evidence_plan=plan,
            read_factories={
                "components": lambda: read_family("components"),
                "index_prices": lambda: read_family("index_prices"),
                "index_returns": lambda: read_family("index_returns"),
                "benchmark_returns": lambda: read_family("benchmark_returns"),
                "fx_rates": lambda: read_family("fx_rates"),
            },
        )
        return results, read_order

    results, read_order = asyncio.run(run_case())

    assert read_order == ["components", "index_prices"]
    assert results == {
        "components": "components-rows",
        "index_prices": "index_prices-rows",
    }


def test_benchmark_market_series_request_scope_binds_paging_to_request() -> None:
    request = BenchmarkMarketSeriesRequest(
        as_of_date=date(2026, 1, 2),
        window={"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2)},
        frequency="daily",
        target_currency="USD",
        series_fields=["index_return", "index_price"],
        page={"page_size": 50},
    )

    scope = benchmark_market_series_request_scope(
        benchmark_id="BMK_GLOBAL_BALANCED",
        request=request,
        cursor={"last_index_id": "IDX_A"},
    )

    assert scope.request_fingerprint
    assert scope.requested_fields == {"index_price", "index_return"}
    assert scope.page_size == 50
    assert scope.cursor_index_id == "IDX_A"


def test_benchmark_market_series_request_scope_rejects_token_scope_mismatch() -> None:
    request = BenchmarkMarketSeriesRequest(
        as_of_date=date(2026, 1, 2),
        window={"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2)},
        frequency="daily",
        target_currency=None,
        series_fields=["index_price"],
    )

    try:
        benchmark_market_series_request_scope(
            benchmark_id="BMK_GLOBAL_BALANCED",
            request=request,
            cursor={"scope_fingerprint": "wrong-scope"},
        )
    except ValueError as exc:
        assert "page token does not match request scope" in str(exc)
    else:
        raise AssertionError("Expected benchmark market-series token scope mismatch")


def test_benchmark_market_series_next_page_token_payload_preserves_scope() -> None:
    request = BenchmarkMarketSeriesRequest(
        as_of_date=date(2026, 1, 2),
        window={"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2)},
        frequency="daily",
        target_currency=None,
        series_fields=["index_price"],
    )
    scope = benchmark_market_series_request_scope(
        benchmark_id="BMK_GLOBAL_BALANCED",
        request=request,
        cursor={},
    )

    assert benchmark_market_series_next_page_token_payload(
        request_scope=scope,
        has_more=True,
        index_ids=["IDX_A", "IDX_B"],
    ) == {
        "scope_fingerprint": scope.request_fingerprint,
        "last_index_id": "IDX_B",
    }
    assert (
        benchmark_market_series_next_page_token_payload(
            request_scope=scope,
            has_more=False,
            index_ids=["IDX_A"],
        )
        is None
    )


def test_benchmark_market_series_index_page_caps_candidate_ids() -> None:
    page = benchmark_market_series_index_page(
        candidate_index_ids=["IDX_A", "IDX_B", "IDX_C"],
        page_size=2,
    )

    assert page.index_ids == ["IDX_A", "IDX_B"]
    assert page.has_more


def test_benchmark_market_series_index_page_marks_terminal_page() -> None:
    page = benchmark_market_series_index_page(
        candidate_index_ids=["IDX_A", "IDX_B"],
        page_size=2,
    )

    assert page.index_ids == ["IDX_A", "IDX_B"]
    assert not page.has_more


def test_benchmark_market_series_page_token_encodes_non_empty_payload() -> None:
    request = BenchmarkMarketSeriesRequest(
        as_of_date=date(2026, 1, 2),
        window={"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2)},
        frequency="daily",
        target_currency=None,
        series_fields=["index_price"],
    )
    scope = benchmark_market_series_request_scope(
        benchmark_id="BMK_GLOBAL_BALANCED",
        request=request,
        cursor={},
    )
    encoded_payloads: list[dict[str, str]] = []

    def encode(payload: dict[str, str]) -> str:
        encoded_payloads.append(payload)
        return "encoded-token"

    assert (
        benchmark_market_series_page_token(
            request_scope=scope,
            has_more=True,
            index_ids=["IDX_A", "IDX_B"],
            encode_page_token=encode,
        )
        == "encoded-token"
    )
    assert encoded_payloads == [
        {
            "scope_fingerprint": scope.request_fingerprint,
            "last_index_id": "IDX_B",
        }
    ]


def test_benchmark_market_series_page_token_suppresses_empty_payload() -> None:
    request = BenchmarkMarketSeriesRequest(
        as_of_date=date(2026, 1, 2),
        window={"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2)},
        frequency="daily",
        target_currency=None,
        series_fields=["index_price"],
    )
    scope = benchmark_market_series_request_scope(
        benchmark_id="BMK_GLOBAL_BALANCED",
        request=request,
        cursor={},
    )

    def encode(_: dict[str, str]) -> str:
        raise AssertionError("Unexpected token encoding for terminal page")

    assert (
        benchmark_market_series_page_token(
            request_scope=scope,
            has_more=False,
            index_ids=["IDX_A"],
            encode_page_token=encode,
        )
        is None
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
