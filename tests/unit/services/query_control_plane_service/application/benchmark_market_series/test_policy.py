"""Unit tests for deterministic benchmark market-series policy."""

from datetime import date

import pytest
from portfolio_common.reference_data_paging import ReferencePageRequest

from services.query_control_plane_service.app.application.benchmark_market_series.policy import (
    build_evidence_plan,
    next_page_token_payload,
    resolve_fx_context,
    resolve_request_scope,
    select_index_page,
)
from services.query_control_plane_service.app.contracts.benchmark_market_series import (
    BenchmarkMarketSeriesRequest,
)
from services.query_control_plane_service.app.contracts.common import IntegrationWindow


def _request(
    *,
    series_fields: list[str] | None = None,
    target_currency: str | None = None,
    page_size: int = 2,
) -> BenchmarkMarketSeriesRequest:
    return BenchmarkMarketSeriesRequest(
        as_of_date=date(2026, 1, 31),
        window=IntegrationWindow(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)),
        frequency="daily",
        target_currency=target_currency,
        series_fields=series_fields or ["index_price", "component_weight"],
        page=ReferencePageRequest(page_size=page_size),
    )


def test_request_scope_is_order_independent_and_restores_cursor() -> None:
    first = resolve_request_scope(
        benchmark_id="BMK_1",
        request=_request(series_fields=["index_price", "component_weight"]),
        cursor={},
    )
    second = resolve_request_scope(
        benchmark_id="BMK_1",
        request=_request(series_fields=["component_weight", "index_price"]),
        cursor={
            "scope_fingerprint": first.request_fingerprint,
            "last_index_id": "IDX_2",
        },
    )

    assert second.request_fingerprint == first.request_fingerprint
    assert second.requested_fields == frozenset({"component_weight", "index_price"})
    assert second.cursor_index_id == "IDX_2"
    assert second.page_size == 2


def test_request_scope_rejects_cursor_from_another_request() -> None:
    with pytest.raises(ValueError, match="does not match request scope"):
        resolve_request_scope(
            benchmark_id="BMK_1",
            request=_request(),
            cursor={"scope_fingerprint": "another-request"},
        )


def test_request_scope_rejects_page_size_change_between_pages() -> None:
    first = resolve_request_scope(
        benchmark_id="BMK_1", request=_request(page_size=2), cursor={}
    )

    with pytest.raises(ValueError, match="does not match request scope"):
        resolve_request_scope(
            benchmark_id="BMK_1",
            request=_request(page_size=3),
            cursor={"scope_fingerprint": first.request_fingerprint},
        )


def test_index_page_and_next_cursor_are_deterministic() -> None:
    scope = resolve_request_scope(benchmark_id="BMK_1", request=_request(), cursor={})
    page = select_index_page(candidate_index_ids=["IDX_1", "IDX_2", "IDX_3"], page_size=2)

    assert page.index_ids == ("IDX_1", "IDX_2")
    assert page.has_more is True
    assert next_page_token_payload(request_scope=scope, index_page=page) == {
        "scope_fingerprint": scope.request_fingerprint,
        "last_index_id": "IDX_2",
    }


def test_last_page_has_no_next_cursor() -> None:
    scope = resolve_request_scope(benchmark_id="BMK_1", request=_request(), cursor={})
    page = select_index_page(candidate_index_ids=["IDX_1"], page_size=2)

    assert next_page_token_payload(request_scope=scope, index_page=page) is None


@pytest.mark.parametrize(
    ("target_currency", "fields", "expected_read", "expected_status"),
    [
        (None, frozenset({"index_price"}), False, "native_component_series_only"),
        (
            "USD",
            frozenset({"fx_rate"}),
            False,
            "native_component_series_with_identity_benchmark_to_target_fx_context",
        ),
        (
            "SGD",
            frozenset({"index_price"}),
            False,
            "native_component_series_without_fx_context_request",
        ),
        ("SGD", frozenset({"fx_rate"}), True, "native_component_series_only"),
    ],
)
def test_fx_context_preserves_native_series_contract(
    target_currency: str | None,
    fields: frozenset[str],
    expected_read: bool,
    expected_status: str,
) -> None:
    context = resolve_fx_context(
        benchmark_currency="USD",
        target_currency=target_currency,
        requested_fields=fields,
    )

    assert context.should_read_fx_rates is expected_read
    assert context.initial_normalization_status == expected_status


def test_evidence_plan_reads_only_requested_sources_in_stable_order() -> None:
    fields = frozenset({"index_return", "benchmark_return", "fx_rate"})
    fx_context = resolve_fx_context(
        benchmark_currency="USD", target_currency="SGD", requested_fields=fields
    )

    plan = build_evidence_plan(requested_fields=fields, fx_context=fx_context)

    assert plan.read_names() == (
        "components",
        "index_returns",
        "benchmark_returns",
        "fx_rates",
    )
