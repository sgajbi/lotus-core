# tests/e2e/test_timeseries_pipeline.py
from decimal import Decimal

import pytest

from .api_client import E2EApiClient
from .assertions import as_decimal


@pytest.fixture(scope="module")
def setup_timeseries_data(clean_db_module, e2e_api_client: E2EApiClient):
    """
    Seed a deterministic 2-day scenario used by analytics input timeseries contracts.
    """
    portfolio_id = "E2E_TS_PORT"

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
                    "security_id": "SEC_EUR_STOCK",
                    "name": "Euro Stock",
                    "isin": "EU123",
                    "currency": "EUR",
                    "product_type": "Equity",
                },
                {
                    "security_id": "CASH",
                    "name": "US Dollar",
                    "isin": "USD_CASH",
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
                {"from_currency": "EUR", "to_currency": "USD", "rate_date": "2025-08-28", "rate": "1.1"},
                {"from_currency": "EUR", "to_currency": "USD", "rate_date": "2025-08-29", "rate": "1.2"},
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
                    "transaction_id": "TS_DEP_01",
                    "portfolio_id": portfolio_id,
                    "instrument_id": "CASH",
                    "security_id": "CASH",
                    "transaction_date": "2025-08-28T00:00:00Z",
                    "transaction_type": "DEPOSIT",
                    "quantity": 5500,
                    "price": 1,
                    "gross_transaction_amount": 5500,
                    "trade_currency": "USD",
                    "currency": "USD",
                },
                {
                    "transaction_id": "TS_BUY_01",
                    "portfolio_id": portfolio_id,
                    "instrument_id": "SEC_EUR_STOCK",
                    "security_id": "SEC_EUR_STOCK",
                    "transaction_date": "2025-08-28T00:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": 100,
                    "price": 50,
                    "gross_transaction_amount": 5000,
                    "trade_currency": "EUR",
                    "currency": "EUR",
                },
                {
                    "transaction_id": "TS_CASH_SETTLE_BUY_01",
                    "portfolio_id": portfolio_id,
                    "instrument_id": "CASH",
                    "security_id": "CASH",
                    "transaction_date": "2025-08-28T00:00:00Z",
                    "transaction_type": "SELL",
                    "quantity": 5500,
                    "price": 1,
                    "gross_transaction_amount": 5500,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {"market_prices": [{"security_id": "SEC_EUR_STOCK", "price_date": "2025-08-28", "price": 52, "currency": "EUR"}]},
    )

    # Day 2
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": "TS_FEE_01",
                    "portfolio_id": portfolio_id,
                    "instrument_id": "CASH",
                    "security_id": "CASH",
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
                {"security_id": "SEC_EUR_STOCK", "price_date": "2025-08-29", "price": 55, "currency": "EUR"},
                {"security_id": "CASH", "price_date": "2025-08-29", "price": 1, "currency": "USD"},
            ]
        },
    )

    # Wait until position state is queryable after day-2 processing.
    e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/positions",
        lambda data: data.get("positions") and len(data["positions"]) >= 2,
        timeout=180,
        fail_message="Pipeline did not produce queryable positions for timeseries setup.",
    )
    return {"portfolio_id": portfolio_id}


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
    assert payload["rows"] == []
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
    assert payload["rows"] == []
    assert "diagnostics" in payload


def test_analytics_input_position_timeseries_contract_day_2_returns_expected_rows(
    setup_timeseries_data, e2e_api_client: E2EApiClient
):
    portfolio_id = setup_timeseries_data["portfolio_id"]
    response = e2e_api_client.post_query(
        f"/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
        _position_timeseries_request("2025-08-29"),
    )
    payload = response.json()
    assert payload["portfolio_id"] == portfolio_id
    assert payload["rows"] == []
    assert "diagnostics" in payload
