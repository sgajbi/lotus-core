import uuid
from decimal import Decimal

import pytest

from .api_client import E2EApiClient
from .assertions import as_decimal

EXPECTED_TIMESERIES_ROWS = {
    "2025-08-28": {
        "SEC_EUR_STOCK": {
            "position_currency": "EUR",
            "quantity": Decimal("100"),
            "ending_market_value_portfolio_currency": Decimal("5200"),
            "valuation_status": "final",
        },
        "CASH_": {
            "position_currency": "USD",
            "quantity": Decimal("0"),
            "ending_market_value_portfolio_currency": Decimal("0"),
            "valuation_status": "restated",
        },
        "total_ending_market_value_portfolio_currency": Decimal("5200"),
        "quality_status_distribution": {"final": 1, "restated": 1},
    },
    "2025-08-29": {
        "SEC_EUR_STOCK": {
            "position_currency": "EUR",
            "quantity": Decimal("100"),
            "ending_market_value_portfolio_currency": Decimal("5500"),
            "valuation_status": "final",
        },
        "CASH_": {
            "position_currency": "USD",
            "quantity": Decimal("-25"),
            "ending_market_value_portfolio_currency": Decimal("-25"),
            "valuation_status": "restated",
        },
        "total_ending_market_value_portfolio_currency": Decimal("5475"),
        "quality_status_distribution": {"final": 1, "restated": 1},
    },
}


@pytest.fixture(scope="module")
def setup_timeseries_data(clean_db_module, e2e_api_client: E2EApiClient):
    """
    Seed a deterministic 2-day scenario used by analytics input timeseries contracts.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_TS_{suffix}"
    stock_security_id = f"SEC_EUR_STOCK_{suffix}"
    cash_security_id = f"CASH_{suffix}"
    stock_isin = f"EU{suffix}"
    cash_isin = f"USD_CASH_{suffix}"
    deposit_tx_id = f"TS_DEP_{suffix}"
    buy_tx_id = f"TS_BUY_{suffix}"
    settle_tx_id = f"TS_CASH_SETTLE_BUY_{suffix}"
    fee_tx_id = f"TS_FEE_{suffix}"

    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2025-01-01",
                    "risk_exposure": "High",
                    "investment_time_horizon": "Long",
                    "portfolio_type": "Discretionary",
                    "booking_center_code": "SG",
                    "client_id": "TS_CIF",
                    "status": "Active",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "security_id": stock_security_id,
                    "name": "Euro Stock",
                    "isin": stock_isin,
                    "currency": "EUR",
                    "product_type": "Equity",
                },
                {
                    "security_id": cash_security_id,
                    "name": "US Dollar",
                    "isin": cash_isin,
                    "currency": "USD",
                    "product_type": "Cash",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/fx-rates",
        {
            "fx_rates": [
                {
                    "from_currency": "EUR",
                    "to_currency": "USD",
                    "rate_date": "2025-08-28",
                    "rate": "1.1",
                },
                {
                    "from_currency": "EUR",
                    "to_currency": "USD",
                    "rate_date": "2025-08-29",
                    "rate": "1.2",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/business-dates",
        {"business_dates": [{"business_date": "2025-08-28"}, {"business_date": "2025-08-29"}]},
    )

    # Day 1
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": deposit_tx_id,
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2025-08-28T00:00:00Z",
                    "transaction_type": "DEPOSIT",
                    "quantity": 5500,
                    "price": 1,
                    "gross_transaction_amount": 5500,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": buy_tx_id,
                    "portfolio_id": portfolio_id,
                    "instrument_id": stock_security_id,
                    "security_id": stock_security_id,
                    "transaction_date": "2025-08-28T00:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": 100,
                    "price": 50,
                    "gross_transaction_amount": 5000,
                    "trade_currency": "EUR",
                    "currency": "EUR",
                },
                {
                    "transaction_id": settle_tx_id,
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2025-08-28T00:00:00Z",
                    "transaction_type": "SELL",
                    "quantity": 5500,
                    "price": 1,
                    "gross_transaction_amount": 5500,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {
                    "security_id": stock_security_id,
                    "price_date": "2025-08-28",
                    "price": 52,
                    "currency": "EUR",
                }
            ]
        },
    )

    # Day 2
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": fee_tx_id,
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": "2025-08-29T00:00:00Z",
                    "transaction_type": "FEE",
                    "quantity": 1,
                    "price": 25,
                    "gross_transaction_amount": 25,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {
                    "security_id": stock_security_id,
                    "price_date": "2025-08-29",
                    "price": 55,
                    "currency": "EUR",
                },
                {
                    "security_id": cash_security_id,
                    "price_date": "2025-08-29",
                    "price": 1,
                    "currency": "USD",
                },
            ]
        },
    )

    # Wait until the actual stock and cash positions have converged after day-2 processing.
    e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/positions",
        lambda data: _has_expected_positions(
            data,
            stock_security_id=stock_security_id,
            cash_security_id=cash_security_id,
        ),
        timeout=240,
        fail_message=(
            "Pipeline did not produce the expected stock and cash positions for timeseries setup."
        ),
    )
    for valuation_date in ("2025-08-28", "2025-08-29"):
        payload = _position_timeseries_request(valuation_date)
        e2e_api_client.poll_for_post_query_data(
            f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
            payload,
            lambda data: _has_expected_timeseries_rows(
                data,
                valuation_date=valuation_date,
                stock_security_id=stock_security_id,
                cash_security_id=cash_security_id,
            ),
            timeout=180,
            fail_message=(
                "Pipeline did not produce analytics position-timeseries rows for "
                f"{valuation_date}."
            ),
        )
    return {
        "portfolio_id": portfolio_id,
        "stock_security_id": stock_security_id,
        "cash_security_id": cash_security_id,
    }


def _position_timeseries_request(day: str) -> dict:
    return {
        "as_of_date": day,
        "window": {"start_date": day, "end_date": day},
        "consumer_system": "lotus-performance",
        "frequency": "daily",
        "dimensions": [],
        "include_cash_flows": True,
        "filters": {},
        "page": {"page_size": 200},
    }


def _sum_portfolio_currency(rows: list[dict]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        total += as_decimal(row["ending_market_value_portfolio_currency"])
    return total


def _has_expected_positions(
    payload: dict,
    *,
    stock_security_id: str,
    cash_security_id: str,
) -> bool:
    positions = payload.get("positions", [])
    stock_row = next(
        (row for row in positions if row.get("security_id") == stock_security_id),
        None,
    )
    cash_row = next((row for row in positions if row.get("security_id") == cash_security_id), None)
    if stock_row is None or cash_row is None:
        return False
    return (
        as_decimal(stock_row["quantity"]) == Decimal("100")
        and as_decimal(cash_row["quantity"]) == Decimal("-25")
    )


def _row_by_security_id(payload: dict, security_id: str) -> dict:
    return next(row for row in payload["rows"] if row["security_id"] == security_id)


def _expected_row_for_security(valuation_date: str, security_id: str) -> dict:
    for prefix, expected in EXPECTED_TIMESERIES_ROWS[valuation_date].items():
        if prefix == "total_ending_market_value_portfolio_currency":
            continue
        if security_id.startswith(prefix):
            return expected
    raise KeyError(f"No expected row configured for {valuation_date=} {security_id=}")


def _assert_timeseries_payload(
    payload: dict,
    *,
    valuation_date: str,
    portfolio_id: str,
    stock_security_id: str,
    cash_security_id: str,
) -> None:
    expected_for_day = EXPECTED_TIMESERIES_ROWS[valuation_date]
    assert payload["portfolio_id"] == portfolio_id
    assert payload["portfolio_currency"] == "USD"
    assert payload["reporting_currency"] == "USD"
    assert payload["frequency"] == "daily"
    assert payload["contract_version"] == "rfc_063_v1"
    assert payload["calendar_id"] == "business_date_calendar"
    assert payload["missing_observation_policy"] == "strict"
    assert payload["resolved_window"] == {"start_date": valuation_date, "end_date": valuation_date}
    assert payload["page"] == {"next_page_token": None}

    diagnostics = payload["diagnostics"]
    assert diagnostics["missing_dates_count"] == 0
    assert diagnostics["stale_points_count"] == 0
    assert diagnostics["quality_status_distribution"] == expected_for_day[
        "quality_status_distribution"
    ]

    rows = payload["rows"]
    assert len(rows) == 2
    assert {row["security_id"] for row in rows} == {stock_security_id, cash_security_id}

    for security_id in (stock_security_id, cash_security_id):
        row = _row_by_security_id(payload, security_id)
        expected = _expected_row_for_security(valuation_date, security_id)
        assert row["valuation_date"] == valuation_date
        assert row["position_currency"] == expected["position_currency"]
        assert row["dimensions"] == {}
        assert row["valuation_status"] == expected["valuation_status"]
        assert as_decimal(row["quantity"]) == expected["quantity"]
        assert (
            as_decimal(row["ending_market_value_portfolio_currency"])
            == expected["ending_market_value_portfolio_currency"]
        )

    assert _sum_portfolio_currency(rows) == expected_for_day[
        "total_ending_market_value_portfolio_currency"
    ]


def _has_expected_timeseries_rows(
    payload: dict,
    *,
    valuation_date: str,
    stock_security_id: str,
    cash_security_id: str,
) -> bool:
    try:
        rows = payload.get("rows", [])
        if len(rows) != 2:
            return False
        stock_row = _row_by_security_id(payload, stock_security_id)
        cash_row = _row_by_security_id(payload, cash_security_id)
        stock_expected = _expected_row_for_security(valuation_date, stock_security_id)
        cash_expected = _expected_row_for_security(valuation_date, cash_security_id)
        return (
            stock_row["valuation_date"] == valuation_date
            and cash_row["valuation_date"] == valuation_date
            and as_decimal(stock_row["quantity"]) == stock_expected["quantity"]
            and as_decimal(cash_row["quantity"]) == cash_expected["quantity"]
            and as_decimal(stock_row["ending_market_value_portfolio_currency"])
            == stock_expected["ending_market_value_portfolio_currency"]
            and as_decimal(cash_row["ending_market_value_portfolio_currency"])
            == cash_expected["ending_market_value_portfolio_currency"]
        )
    except (KeyError, StopIteration):
        return False


def test_analytics_input_timeseries_contract_day_1_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        _position_timeseries_request("2025-08-28"),
    )
    payload = response.json()
    _assert_timeseries_payload(
        payload,
        valuation_date="2025-08-28",
        portfolio_id=portfolio_id,
        stock_security_id=setup_timeseries_data["stock_security_id"],
        cash_security_id=setup_timeseries_data["cash_security_id"],
    )


def test_analytics_input_timeseries_contract_day_2_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        _position_timeseries_request("2025-08-29"),
    )
    payload = response.json()
    _assert_timeseries_payload(
        payload,
        valuation_date="2025-08-29",
        portfolio_id=portfolio_id,
        stock_security_id=setup_timeseries_data["stock_security_id"],
        cash_security_id=setup_timeseries_data["cash_security_id"],
    )


def test_analytics_input_position_timeseries_contract_day_2_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    day_1_response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        _position_timeseries_request("2025-08-28"),
    )
    day_1_payload = day_1_response.json()
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        _position_timeseries_request("2025-08-29"),
    )
    payload = response.json()
    _assert_timeseries_payload(
        day_1_payload,
        valuation_date="2025-08-28",
        portfolio_id=portfolio_id,
        stock_security_id=setup_timeseries_data["stock_security_id"],
        cash_security_id=setup_timeseries_data["cash_security_id"],
    )
    _assert_timeseries_payload(
        payload,
        valuation_date="2025-08-29",
        portfolio_id=portfolio_id,
        stock_security_id=setup_timeseries_data["stock_security_id"],
        cash_security_id=setup_timeseries_data["cash_security_id"],
    )
