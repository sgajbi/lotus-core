from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .api_client import E2EApiClient
from .assertions import as_decimal


def _matches_decimal(value: Any, expected: Decimal) -> bool:
    try:
        return as_decimal(value) == expected
    except (InvalidOperation, TypeError, ValueError):
        return False


def _position_matches_expected(row: dict[str, Any], expected: dict[str, Decimal]) -> bool:
    valuation = row.get("valuation")
    if not isinstance(valuation, dict):
        return False
    return (
        _matches_decimal(row.get("quantity"), expected["quantity"])
        and _matches_decimal(row.get("cost_basis"), expected["cost_basis"])
        and _matches_decimal(valuation.get("market_value"), expected["market_value"])
    )


def assert_positions_state(
    e2e_api_client: E2EApiClient,
    *,
    portfolio_id: str,
    as_of_date: str,
    expected_positions: dict[str, dict[str, Decimal]],
) -> None:
    def _has_expected_positions(data: dict) -> bool:
        positions = data.get("positions", [])
        if len(positions) != len(expected_positions):
            return False
        by_security = {row["security_id"]: row for row in positions}
        if set(by_security) != set(expected_positions):
            return False
        for security_id, expected in expected_positions.items():
            if not _position_matches_expected(by_security[security_id], expected):
                return False
        return True

    payload = e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/positions?as_of_date={as_of_date}",
        _has_expected_positions,
        timeout=180,
        fail_message=f"Positions did not converge to the expected state for {as_of_date}.",
    )

    positions = payload["positions"]
    by_security = {row["security_id"]: row for row in positions}
    assert set(by_security) == set(expected_positions)
    for security_id, expected in expected_positions.items():
        row = by_security[security_id]
        assert as_decimal(row["quantity"]) == expected["quantity"]
        assert as_decimal(row["cost_basis"]) == expected["cost_basis"]
        assert as_decimal(row["valuation"]["market_value"]) == expected["market_value"]


def assert_portfolio_timeseries_value(
    poll_db_until,
    *,
    portfolio_id: str,
    date: str,
    expected_eod_market_value: Decimal,
) -> None:
    query = (
        "SELECT eod_market_value FROM portfolio_timeseries "
        "WHERE portfolio_id = :pid AND date = :date"
    )
    params = {"pid": portfolio_id, "date": date}
    poll_db_until(
        query,
        lambda r: r is not None and r.eod_market_value == expected_eod_market_value,
        params,
    )
