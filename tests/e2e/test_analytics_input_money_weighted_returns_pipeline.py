# tests/e2e/test_analytics_input_money_weighted_returns_pipeline.py
import pytest
from datetime import date, timedelta

from .api_client import E2EApiClient
from .assertions import assert_legacy_endpoint_status

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
    current_date = date(2025, 8, 1)
    while current_date <= date(2025, 8, 31):
        all_dates.append({"business_date": current_date.isoformat()})
        current_date += timedelta(days=1)
    if all_dates:
        e2e_api_client.ingest("/ingest/business-dates", {"business_dates": all_dates})

    # --- Ingest transactions and prices ---
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [
        {"transaction_id": "MWR_DEPOSIT_01", "portfolio_id": portfolio_id, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-01T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000, "price": 1, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "MWR_DEPOSIT_02", "portfolio_id": portfolio_id, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-15T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 200, "price": 1, "gross_transaction_amount": 200, "trade_currency": "USD", "currency": "USD"}
    ]})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"security_id": "CASH_USD", "price_date": "2025-08-01", "price": 1.0, "currency": "USD"},
        {"security_id": "CASH_USD", "price_date": "2025-08-31", "price": 1.04166667, "currency": "USD"}
    ]})
    
    # Poll until transactions are persisted before querying downstream analytics-input endpoint.
    poll_db_until(
        query="SELECT count(*) FROM transactions WHERE portfolio_id = :pid",
        params={"pid": portfolio_id},
        validation_func=lambda r: r is not None and r[0] >= 2,
        timeout=90,
        fail_message="Pipeline did not persist MWR fixture transactions."
    )
    
    return {"portfolio_id": portfolio_id}

def test_analytics_input_mwr_contract_dataset_is_queryable(setup_mwr_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core MWR endpoint is hard-disabled and callers are expected
    to use lotus-performance for analytics calculations.
    """
    # ARRANGE
    portfolio_id = setup_mwr_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/performance/mwr"
    
    request_payload = {
        "scope": { "as_of_date": "2025-08-31" },
        "periods": [
            { "type": "EXPLICIT", "name": "TestPeriod", "from": "2025-08-01", "to": "2025-08-31" }
        ],
        "options": { "annualize": True }
    }
    
    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)
    assert_legacy_endpoint_status(response)
