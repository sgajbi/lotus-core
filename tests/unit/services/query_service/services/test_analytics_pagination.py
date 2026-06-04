from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from src.services.query_service.app.services.analytics_pagination import (
    AnalyticsPaginationError,
    portfolio_timeseries_cursor_date,
    portfolio_timeseries_diagnostics,
    position_timeseries_cursor,
    position_timeseries_diagnostics,
    position_timeseries_next_page_token,
)


def test_portfolio_cursor_date_rejects_mismatched_scope() -> None:
    with pytest.raises(AnalyticsPaginationError, match="Page token does not match request scope"):
        portfolio_timeseries_cursor_date(
            page_token="opaque",
            request_scope_fingerprint="scope-1",
            decode_page_token=lambda _: {"scope_fingerprint": "scope-2"},
        )


def test_position_cursor_parses_snapshot_epoch_and_security_id() -> None:
    cursor = position_timeseries_cursor(
        page_token="opaque",
        request_scope_fingerprint="scope-1",
        decode_page_token=lambda _: {
            "valuation_date": "2025-01-31",
            "security_id": "SEC_A",
            "snapshot_epoch": "7",
            "scope_fingerprint": "scope-1",
        },
    )

    assert cursor.cursor_date == date(2025, 1, 31)
    assert cursor.cursor_security_id == "SEC_A"
    assert cursor.snapshot_epoch == 7


def test_position_next_page_token_encodes_last_row_scope() -> None:
    encoded_payloads: list[dict] = []

    token = position_timeseries_next_page_token(
        has_more=True,
        rows_page=[
            SimpleNamespace(valuation_date=date(2025, 1, 30), security_id="SEC_A"),
            SimpleNamespace(valuation_date=date(2025, 1, 31), security_id="SEC_B"),
        ],
        snapshot_epoch=3,
        request_scope_fingerprint="scope-1",
        encode_page_token=lambda payload: encoded_payloads.append(payload) or "token-1",
    )

    assert token == "token-1"
    assert encoded_payloads == [
        {
            "valuation_date": "2025-01-31",
            "security_id": "SEC_B",
            "snapshot_epoch": 3,
            "scope_fingerprint": "scope-1",
        }
    ]


def test_portfolio_diagnostics_counts_missing_and_stale_dates() -> None:
    diagnostics = portfolio_timeseries_diagnostics(
        quality_distribution={"final": 2, "restated": 1},
        expected_business_dates=[date(2025, 1, 30), date(2025, 1, 31)],
        observed_dates=[date(2025, 1, 31)],
    )

    assert diagnostics.missing_dates_count == 1
    assert diagnostics.stale_points_count == 1
    assert diagnostics.expected_business_dates_count == 2
    assert diagnostics.returned_observation_dates_count == 1
    assert diagnostics.cash_flows_included is True


def test_position_diagnostics_preserves_requested_dimensions_and_cash_flow_flag() -> None:
    diagnostics = position_timeseries_diagnostics(
        quality_distribution={"final": 1, "restated": 2},
        dimensions=["asset_class", "sector"],
        include_cash_flows=False,
    )

    assert diagnostics.stale_points_count == 2
    assert diagnostics.requested_dimensions == ["asset_class", "sector"]
    assert diagnostics.cash_flows_included is False
