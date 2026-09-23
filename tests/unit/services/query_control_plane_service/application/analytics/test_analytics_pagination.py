from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.request_fingerprints import request_fingerprint

from src.services.query_control_plane_service.app.application.analytics.analytics_pagination import (  # noqa: E501
    AnalyticsPaginationError,
    portfolio_business_calendar_scope,
    portfolio_timeseries_cursor_date,
    portfolio_timeseries_diagnostics,
    portfolio_timeseries_scope_fingerprint,
    position_timeseries_cursor,
    position_timeseries_diagnostics,
    position_timeseries_next_page_token,
    position_timeseries_scope_fingerprint,
)
from src.services.query_control_plane_service.app.contracts.analytics_inputs import (
    AnalyticsWindow,
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)


@pytest.mark.asyncio
async def test_portfolio_calendar_scope_keeps_window_and_global_horizon_coherent() -> None:
    reader = SimpleNamespace(
        get_business_calendar_scope=AsyncMock(
            return_value=(
                [date(2025, 1, 2), date(2025, 1, 31), date(2025, 5, 30)],
                True,
                date(2019, 12, 31),
            )
        )
    )

    (
        window_dates,
        horizon_dates,
        calendar_present,
        predecessor,
    ) = await portfolio_business_calendar_scope(
        reader,
        AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
        date(2020, 1, 1),
        date(2025, 5, 31),
    )

    reader.get_business_calendar_scope.assert_awaited_once_with(
        start_date=date(2020, 1, 1),
        end_date=date(2025, 5, 31),
    )
    assert window_dates == [date(2025, 1, 2), date(2025, 1, 31)]
    assert horizon_dates == [date(2025, 1, 2), date(2025, 1, 31), date(2025, 5, 30)]
    assert calendar_present is True
    assert predecessor == date(2019, 12, 31)


def test_portfolio_cursor_date_rejects_mismatched_scope() -> None:
    with pytest.raises(AnalyticsPaginationError, match="Page token does not match request scope"):
        portfolio_timeseries_cursor_date(
            page_token="opaque",
            request_scope_fingerprint="scope-1",
            decode_page_token=lambda _: {"scope_fingerprint": "scope-2"},
        )


def test_portfolio_scope_changes_when_performance_horizon_calendar_changes() -> None:
    window = AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31")
    request = PortfolioAnalyticsTimeseriesRequest(as_of_date="2025-05-31", window=window)
    common = {
        "portfolio_id": "P1",
        "request": request,
        "resolved_window": window,
        "reporting_currency": "USD",
        "expected_business_dates": [date(2025, 1, 31)],
        "business_calendar_present": True,
    }

    january_horizon = portfolio_timeseries_scope_fingerprint(
        **common,
        performance_horizon_business_dates=[date(2025, 1, 31)],
    )
    may_horizon = portfolio_timeseries_scope_fingerprint(
        **common,
        performance_horizon_business_dates=[date(2025, 1, 31), date(2025, 5, 30)],
    )

    assert january_horizon != may_horizon


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


def test_position_scope_changes_when_governed_calendar_membership_changes() -> None:
    window = AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31")
    request = PositionAnalyticsTimeseriesRequest(
        as_of_date="2025-01-31",
        window=window,
    )
    initial_scope = position_timeseries_scope_fingerprint(
        portfolio_id="P1",
        request=request,
        resolved_window=window,
        reporting_currency="USD",
        expected_business_dates=[date(2025, 1, 2)],
        business_calendar_present=True,
    )
    updated_scope = position_timeseries_scope_fingerprint(
        portfolio_id="P1",
        request=request,
        resolved_window=window,
        reporting_currency="USD",
        expected_business_dates=[date(2025, 1, 2), date(2025, 1, 3)],
        business_calendar_present=True,
    )

    assert updated_scope != initial_scope


def test_position_scope_changes_when_calendar_fallback_activates() -> None:
    window = AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31")
    request = PositionAnalyticsTimeseriesRequest(as_of_date="2025-01-31", window=window)

    fallback_scope = position_timeseries_scope_fingerprint(
        portfolio_id="P1",
        request=request,
        resolved_window=window,
        reporting_currency="USD",
        expected_business_dates=[],
        business_calendar_present=False,
    )
    governed_scope = position_timeseries_scope_fingerprint(
        portfolio_id="P1",
        request=request,
        resolved_window=window,
        reporting_currency="USD",
        expected_business_dates=[],
        business_calendar_present=True,
    )

    assert governed_scope != fallback_scope


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


def test_portfolio_diagnostics_keeps_authoritative_restatements_current() -> None:
    diagnostics = portfolio_timeseries_diagnostics(
        quality_distribution={"final": 2, "restated": 1},
        expected_business_dates=[date(2025, 1, 30), date(2025, 1, 31)],
        observed_dates=[date(2025, 1, 31)],
    )

    assert diagnostics.missing_dates_count == 1
    assert diagnostics.stale_points_count == 0
    assert diagnostics.expected_business_dates_count == 2
    assert diagnostics.expected_business_dates_digest == request_fingerprint(
        {"business_dates": ["2025-01-30", "2025-01-31"]}
    )
    assert diagnostics.returned_observation_dates_count == 1
    assert diagnostics.cash_flows_included is True


def test_position_diagnostics_preserves_current_restatement_and_request_metadata() -> None:
    diagnostics = position_timeseries_diagnostics(
        quality_distribution={"final": 1, "restated": 2},
        missing_dates_count=1,
        dimensions=["asset_class", "sector"],
        include_cash_flows=False,
    )

    assert diagnostics.missing_dates_count == 1
    assert diagnostics.stale_points_count == 0
    assert diagnostics.requested_dimensions == ["asset_class", "sector"]
    assert diagnostics.cash_flows_included is False
