from __future__ import annotations

from decimal import Decimal

from .api_client import E2EApiClient
from .assertions import as_decimal


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
            row = by_security[security_id]
            if as_decimal(row["quantity"]) != expected["quantity"]:
                return False
            if as_decimal(row["cost_basis"]) != expected["cost_basis"]:
                return False
            if as_decimal(row["valuation"]["market_value"]) != expected["market_value"]:
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
