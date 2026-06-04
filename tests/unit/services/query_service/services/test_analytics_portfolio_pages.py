from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_service.app.services.analytics_portfolio_pages import (
    AnalyticsPortfolioPageError,
    portfolio_observation_next_page_token,
    portfolio_observation_page_scope,
    portfolio_row_buckets,
    portfolio_to_reporting_observation_rate,
    position_to_portfolio_observation_rate,
)


def test_portfolio_observation_page_scope_applies_cursor_and_has_more_flag() -> None:
    scope = portfolio_observation_page_scope(
        observed_dates=[date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)],
        cursor_date=date(2025, 1, 1),
        page_size=1,
    )

    assert scope.page_dates == [date(2025, 1, 2)]
    assert scope.has_more is True


def test_portfolio_row_buckets_keeps_only_page_dates() -> None:
    rows = [
        SimpleNamespace(valuation_date=date(2025, 1, 1), security_id="SEC_A"),
        SimpleNamespace(valuation_date=date(2025, 1, 2), security_id="SEC_B"),
        SimpleNamespace(valuation_date=date(2025, 1, 3), security_id="SEC_C"),
    ]

    buckets = portfolio_row_buckets(
        page_dates=[date(2025, 1, 1), date(2025, 1, 3)],
        position_rows=rows,
    )

    assert buckets == {
        date(2025, 1, 1): [rows[0]],
        date(2025, 1, 3): [rows[2]],
    }


def test_portfolio_to_reporting_observation_rate_requires_cross_rate() -> None:
    with pytest.raises(AnalyticsPortfolioPageError, match="Missing FX rate for EUR/USD"):
        portfolio_to_reporting_observation_rate(
            valuation_date=date(2025, 1, 31),
            portfolio_currency="EUR",
            reporting_currency="USD",
            portfolio_to_reporting_rates={},
        )


def test_position_to_portfolio_observation_rate_returns_identity_without_position_currency() -> (
    None
):
    assert position_to_portfolio_observation_rate(
        row=SimpleNamespace(position_currency=None),
        valuation_date=date(2025, 1, 31),
        portfolio_currency="USD",
        position_to_portfolio_rates={},
    ) == Decimal("1")


def test_portfolio_observation_next_page_token_encodes_last_page_date() -> None:
    encoded_payloads: list[dict] = []
    scope = portfolio_observation_page_scope(
        observed_dates=[date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)],
        cursor_date=None,
        page_size=2,
    )

    token = portfolio_observation_next_page_token(
        page_scope=scope,
        snapshot_epoch=7,
        request_scope_fingerprint="scope-1",
        encode_page_token=lambda payload: encoded_payloads.append(payload) or "token-1",
    )

    assert token == "token-1"
    assert encoded_payloads == [
        {
            "valuation_date": "2025-01-02",
            "snapshot_epoch": 7,
            "scope_fingerprint": "scope-1",
        }
    ]
