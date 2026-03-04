# tests/e2e/test_analytics_input_review_pipeline.py
import pytest
from .api_client import E2EApiClient

# --- Test Data Constants ---
PORTFOLIO_ID = "E2E_REVIEW_01"
AS_OF_DATE = "2025-08-30"

@pytest.fixture(scope="module")
def setup_review_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the full
    portfolio review E2E test.
    """
    # 1. Ingest prerequisite data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolio_id": PORTFOLIO_ID, "base_currency": "USD", "open_date": "2025-01-01", "client_id": "REVIEW_CIF", "status": "ACTIVE", "risk_exposure":"Growth", "investment_time_horizon":"b", "portfolio_type":"Discretionary", "booking_center_code":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [
        {"security_id": "CASH_USD", "name": "US Dollar", "isin": "CASH_USD_ISIN", "currency": "USD", "product_type": "Cash", "asset_class": "Cash"},
        {"security_id": "SEC_AAPL", "name": "Apple Inc.", "isin": "US_AAPL_REVIEW", "currency": "USD", "product_type": "Equity", "asset_class": "Equity"},
        {"security_id": "SEC_BOND", "name": "US Treasury Bond", "isin": "US_BOND_REVIEW", "currency": "USD", "product_type": "Bond", "asset_class": "Fixed Income"}
    ]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"business_date": "2025-08-20"}, {"business_date": "2025-08-25"}, {"business_date": AS_OF_DATE}]})

    # 2. Ingest transactions to build a history
    transactions = [
        {"transaction_id": "REVIEW_DEPOSIT_01", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-20T09:00:00Z", "transaction_type": "DEPOSIT", "quantity": 100000, "price": 1, "gross_transaction_amount": 100000, "trade_currency": "USD", "currency": "USD"},
        
        # Apple Purchase
        {"transaction_id": "REVIEW_BUY_AAPL", "portfolio_id": PORTFOLIO_ID, "instrument_id": "AAPL", "security_id": "SEC_AAPL", "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150, "gross_transaction_amount": 15000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_CASH_SETTLE_AAPL", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "SELL", "quantity": 15000, "price": 1, "gross_transaction_amount": 15000, "trade_currency": "USD", "currency": "USD"},
        
        # Bond Purchase
        {"transaction_id": "REVIEW_BUY_BOND", "portfolio_id": PORTFOLIO_ID, "instrument_id": "UST", "security_id": "SEC_BOND", "transaction_date": "2025-08-20T11:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 980, "gross_transaction_amount": 9800, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_CASH_SETTLE_BOND", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-20T11:00:00Z", "transaction_type": "SELL", "quantity": 9800, "price": 1, "gross_transaction_amount": 9800, "trade_currency": "USD", "currency": "USD"},

        # Dividend Payment
        {"transaction_id": "REVIEW_DIV_AAPL", "portfolio_id": PORTFOLIO_ID, "instrument_id": "AAPL", "security_id": "SEC_AAPL", "transaction_date": "2025-08-25T10:00:00Z", "transaction_type": "DIVIDEND", "quantity": 0, "price": 0, "gross_transaction_amount": 120, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_CASH_SETTLE_DIV", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-25T10:00:00Z", "transaction_type": "BUY", "quantity": 120, "price": 1, "gross_transaction_amount": 120, "trade_currency": "USD", "currency": "USD"}
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})
    
    # 3. Ingest market prices for valuation
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"security_id": "SEC_AAPL", "price_date": AS_OF_DATE, "price": 160.0, "currency": "USD"},
        {"security_id": "SEC_BOND", "price_date": AS_OF_DATE, "price": 995.0, "currency": "USD"},
        {"security_id": "CASH_USD", "price_date": AS_OF_DATE, "price": 1.0, "currency": "USD"}
    ]})
    
    # 4. Poll until the final day's timeseries is generated
    poll_db_until(
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": PORTFOLIO_ID, "date": AS_OF_DATE},
        validation_func=lambda r: r is not None,
        timeout=180,
        fail_message=f"Pipeline did not generate portfolio_timeseries for {AS_OF_DATE}."
    )
    return {"portfolio_id": PORTFOLIO_ID}


def test_analytics_input_review_contract_returns_expected_dataset(setup_review_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core review endpoint is hard-disabled and directs callers to lotus-report.
    """
    portfolio_id = setup_review_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/review"
    request_payload = {
        "as_of_date": AS_OF_DATE,
        "sections": [
            "OVERVIEW", "HOLDINGS", "TRANSACTIONS", "PERFORMANCE", "RISK_ANALYTICS"
        ]
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()["detail"]

    # ASSERT
    assert response.status_code == 410
    assert data["code"] == "LOTUS_CORE_LEGACY_ENDPOINT_REMOVED"
    assert data["target_service"] == "lotus-report"
    assert data["target_endpoint"] == "/reports/portfolios/{portfolio_id}/review"


def test_analytics_input_review_contract_handles_empty_portfolio(clean_db, e2e_api_client: E2EApiClient):
    """
    Verifies empty-portfolio calls also receive 410 migration guidance.
    """
    # ARRANGE
    empty_portfolio_id = "E2E_REVIEW_EMPTY_01"
    as_of = "2025-08-31"
    
    # 1. Ingest only the portfolio and a business date
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolio_id": empty_portfolio_id, "base_currency": "USD", "open_date": "2025-01-01", "client_id": "REVIEW_EMPTY_CIF", "status": "ACTIVE", "risk_exposure":"Balanced", "investment_time_horizon":"c", "portfolio_type":"d", "booking_center_code":"e"}]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"business_date": as_of}]})
    
    # 2. Wait for the portfolio to be queryable
    e2e_api_client.poll_for_data(
        f"/portfolios?portfolio_id={empty_portfolio_id}",
        lambda data: data and data.get("portfolios") and len(data["portfolios"]) == 1
    )

    # 3. Define the request for the review endpoint
    api_url = f"/portfolios/{empty_portfolio_id}/review"
    request_payload = {
        "as_of_date": as_of,
        "sections": ["OVERVIEW", "HOLDINGS", "TRANSACTIONS", "PERFORMANCE", "RISK_ANALYTICS"]
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()["detail"]

    # ASSERT
    assert response.status_code == 410
    assert data["code"] == "LOTUS_CORE_LEGACY_ENDPOINT_REMOVED"
    assert data["target_service"] == "lotus-report"
    assert data["target_endpoint"] == "/reports/portfolios/{portfolio_id}/review"
