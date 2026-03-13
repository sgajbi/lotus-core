import time
import uuid
from decimal import Decimal

import pytest

from .api_client import E2EApiClient
from .assertions import as_decimal


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
        start = time.time()
        last_response = None
        while time.time() - start < 180:
            response = e2e_api_client.post_query(
                f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
                payload,
                raise_for_status=False,
            )
            if response.status_code == 200:
                last_response = response.json()
                if _has_stock_timeseries_row(last_response, valuation_date=valuation_date):
                    break
            time.sleep(2)
        else:
            pytest.fail(
                "Pipeline did not produce analytics position-timeseries rows for "
                f"{valuation_date}. Last response: {last_response}"
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


def _has_stock_timeseries_row(payload: dict, *, valuation_date: str) -> bool:
    for row in payload.get("rows", []):
        if (
            row.get("security_id", "").startswith("SEC_EUR_STOCK_")
            and row.get("valuation_date") == valuation_date
        ):
            return True
    return False


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
    return as_decimal(stock_row["quantity"]) == Decimal("100")


def test_analytics_input_timeseries_contract_day_1_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        _position_timeseries_request("2025-08-28"),
    )
    payload = response.json()
    assert payload["portfolio_id"] == portfolio_id
    assert "rows" in payload
    assert payload["rows"]
    stock_row = next(
        row
        for row in payload["rows"]
        if row["security_id"] == setup_timeseries_data["stock_security_id"]
    )
    assert as_decimal(stock_row["quantity"]) == Decimal("100")
    assert as_decimal(stock_row["ending_market_value_portfolio_currency"]) > Decimal("0")
    assert stock_row["valuation_date"] == "2025-08-28"
    assert "diagnostics" in payload


def test_analytics_input_timeseries_contract_day_2_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        _position_timeseries_request("2025-08-29"),
    )
    payload = response.json()
    assert payload["portfolio_id"] == portfolio_id
    assert "rows" in payload
    assert payload["rows"]
    stock_row = next(
        row
        for row in payload["rows"]
        if row["security_id"] == setup_timeseries_data["stock_security_id"]
    )
    assert as_decimal(stock_row["quantity"]) == Decimal("100")
    assert as_decimal(stock_row["ending_market_value_portfolio_currency"]) > Decimal("0")
    assert stock_row["valuation_date"] == "2025-08-29"
    assert "diagnostics" in payload


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
    assert payload["portfolio_id"] == portfolio_id
    assert payload["rows"]
    day_1_stock = next(
        row
        for row in day_1_payload["rows"]
        if row["security_id"] == setup_timeseries_data["stock_security_id"]
    )
    day_2_stock = next(
        row
        for row in payload["rows"]
        if row["security_id"] == setup_timeseries_data["stock_security_id"]
    )
    assert as_decimal(day_2_stock["ending_market_value_portfolio_currency"]) > as_decimal(
        day_1_stock["ending_market_value_portfolio_currency"]
    )
    assert "diagnostics" in payload
