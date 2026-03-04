# tests/e2e/test_mwr_pipeline.py
import pytest
import time
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date, timedelta

from .api_client import E2EApiClient
from tests.conftest import poll_db_until

@pytest.fixture(scope="module")
def setup_mwr_data(clean_db_module, db_engine, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture to ingest data for an MWR scenario and wait for the
    backend pipeline to generate the necessary time-series data using a robust
    sequential ingestion pattern.
    """
    portfolio_id = "E2E_MWR_PERF_01"
    
    # --- Ingest Prerequisite Data ---
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolio_id": portfolio_id, "base_currency": "USD", "open_date": "2025-01-01", "client_id": "MWR_CIF", "status": "ACTIVE", "risk_exposure":"a", "investment_time_horizon":"b", "portfolio_type":"c", "booking_center_code":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [{"security_id": "CASH_USD", "name": "US Dollar", "isin": "CASH_USD_ISIN", "currency": "USD", "product_type": "Cash"}]})

    # Ingest all business dates up front to ensure schedulers can work
    all_dates = []
    current_date = date(2025, 1, 1)
    while current_date <= date(2025, 1, 31):
        all_dates.append({"business_date": current_date.isoformat()})
        current_date += timedelta(days=1)
    if all_dates:
        e2e_api_client.ingest("/ingest/business-dates", {"business_dates": all_dates})

    # --- Ingest transactions and prices ---
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [
        {"transaction_id": "MWR_DEPOSIT_01", "portfolio_id": portfolio_id, "instrument_id": "CASH", "security_id": "CASH_USD", "transaction_date": "2025-01-01T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000, "price": 1, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "MWR_DEPOSIT_02", "portfolio_id": portfolio_id, "instrument_id": "CASH", "security_id": "CASH_USD", "transaction_date": "2025-01-15T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 200, "price": 1, "gross_transaction_amount": 200, "trade_currency": "USD", "currency": "USD"}
    ]})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"security_id": "CASH_USD", "price_date": "2025-01-01", "price": 1.0, "currency": "USD"},
        {"security_id": "CASH_USD", "price_date": "2025-01-31", "price": 1.04166667, "currency": "USD"}
    ]})
    
    # Poll until the timeseries for the last day is fully generated.
    poll_db_until(
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": portfolio_id, "date": "2025-01-31"},
        validation_func=lambda r: r is not None,
        timeout=90,
        fail_message="Pipeline did not generate portfolio_timeseries for the final day."
    )
    
    return {"portfolio_id": portfolio_id}

def test_mwr_api_calculates_correctly(setup_mwr_data, e2e_api_client: E2EApiClient):
    """
    Tests the full MWR pipeline by calling the new endpoint and verifying the result.
    The test scenario is:
    - Jan 1: Begin MV = 0, Contribution = 1000
    - Jan 15: Contribution = 200
    - Jan 31: End MV = 1250 (which is 1200 * 1.04166667 price)
    """
    # ARRANGE
    portfolio_id = setup_mwr_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/performance/mwr"
    
    request_payload = {
        "scope": { "as_of_date": "2025-01-31" },
        "periods": [
            { "type": "EXPLICIT", "name": "TestPeriod", "from": "2025-01-01", "to": "2025-01-31" }
        ],
        "options": { "annualize": True }
    }
    
    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()
    
    # ASSERT
    assert response.status_code == 200
    
    assert "TestPeriod" in data["summary"]
    result = data["summary"]["TestPeriod"]

    # Assert attributes are correct
    attrs = result["attributes"]
    assert Decimal(attrs["begin_market_value"]).quantize(Decimal("0.01")) == Decimal("0.00")
    assert Decimal(attrs["end_market_value"]).quantize(Decimal("0.01")) == Decimal("1250.00")
    assert Decimal(attrs["external_contributions"]) == Decimal("1200.00")
    assert Decimal(attrs["external_withdrawals"]) == Decimal("0.00")
    assert attrs["cashflow_count"] == 2

    # Assert MWR calculation is correct
    # The annualized IRR for this cashflow series is ~71.28%
    assert result["mwr"] is not None
    assert pytest.approx(result["mwr"], abs=1e-4) == 0.7128
    
    # Annualized MWR should be null for a period < 1 year
    assert result["mwr_annualized"] is None