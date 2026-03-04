# tests/e2e/test_concentration_pipeline.py
import pytest
from .api_client import E2EApiClient
from .assertions import assert_legacy_endpoint_status

# --- Test Data Constants ---
PORTFOLIO_ID = "E2E_CONC_01"
AS_OF_DATE = "2025-08-31"
SEC_A_ID = "SEC_CONC_A"
SEC_B_ID = "SEC_CONC_B"
SEC_C_ID = "SEC_CONC_C"

@pytest.fixture(scope="module")
def setup_concentration_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the full
    concentration E2E test and waits for the pipeline to complete.
    """
    # 1. Ingest prerequisite data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolio_id": PORTFOLIO_ID, "base_currency": "USD", "open_date": "2025-01-01", "client_id": "CONC_CIF", "status": "ACTIVE", "risk_exposure":"a", "investment_time_horizon":"b", "portfolio_type":"c", "booking_center_code":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [
        {"security_id": SEC_A_ID, "name": "CONC_A", "isin": "ISIN_CONC_A", "currency": "USD", "product_type": "Equity", "asset_class": "Equity", "issuer_id": "ISS_XYZ", "ultimate_parent_issuer_id": "PARENT_XYZ"},
        {"security_id": SEC_B_ID, "name": "CONC_B", "isin": "ISIN_CONC_B", "currency": "USD", "product_type": "Equity", "asset_class": "Equity", "issuer_id": "ISS_XYZ_SUB", "ultimate_parent_issuer_id": "PARENT_XYZ"},
        {"security_id": SEC_C_ID, "name": "CONC_C", "isin": "ISIN_CONC_C", "currency": "USD", "product_type": "Equity", "asset_class": "Equity", "issuer_id": "ISS_ABC", "ultimate_parent_issuer_id": "PARENT_ABC"}
    ]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"business_date": AS_OF_DATE}]})

    # 2. Ingest transactions to create positions
    transactions = [
        {"transaction_id": "CONC_BUY_A", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CONC_A_TICKER", "security_id": SEC_A_ID, "transaction_date": f"{AS_OF_DATE}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 1, "gross_transaction_amount": 100, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "CONC_BUY_B", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CONC_B_TICKER", "security_id": SEC_B_ID, "transaction_date": f"{AS_OF_DATE}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 1, "gross_transaction_amount": 100, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "CONC_BUY_C", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CONC_C_TICKER", "security_id": SEC_C_ID, "transaction_date": f"{AS_OF_DATE}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 1, "gross_transaction_amount": 100, "trade_currency": "USD", "currency": "USD"}
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})
    
    # 3. Ingest market prices that will result in the desired weights
    prices = [
        {"security_id": SEC_A_ID, "price_date": AS_OF_DATE, "price": 600.0, "currency": "USD"}, # 60,000
        {"security_id": SEC_B_ID, "price_date": AS_OF_DATE, "price": 250.0, "currency": "USD"}, # 25,000
        {"security_id": SEC_C_ID, "price_date": AS_OF_DATE, "price": 150.0, "currency": "USD"}  # 15,000
    ] # Total Market Value = 100,000
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": prices})
    
    # 4. Poll until the final snapshot is valued for all positions
    poll_db_until(
        query="SELECT count(*) FROM daily_position_snapshots WHERE portfolio_id = :pid AND date = :date AND valuation_status = 'VALUED_CURRENT'",
        params={"pid": PORTFOLIO_ID, "date": AS_OF_DATE},
        validation_func=lambda r: r is not None and r[0] == 3,
        timeout=120,
        fail_message=f"Pipeline did not value all 3 positions for {AS_OF_DATE}."
    )
    return {"portfolio_id": PORTFOLIO_ID}

def test_bulk_concentration_e2e(setup_concentration_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core concentration endpoint is hard-disabled and directs callers to lotus-risk.
    """
    portfolio_id = setup_concentration_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/concentration"
    request_payload = {
        "scope": {"as_of_date": AS_OF_DATE},
        "metrics": ["BULK"],
        "options": {"bulk_top_n": [2]}
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)

    # ASSERT
    assert_legacy_endpoint_status(
        response,
        target_service="lotus-risk",
        target_endpoint="/analytics/risk/concentration",
    )

def test_issuer_concentration_e2e(setup_concentration_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core concentration endpoint is hard-disabled and directs callers to lotus-risk.
    """
    portfolio_id = setup_concentration_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/concentration"
    request_payload = {
        "scope": {"as_of_date": AS_OF_DATE},
        "metrics": ["ISSUER"],
        "options": {"issuer_top_n": 5}
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)

    # ASSERT
    assert_legacy_endpoint_status(
        response,
        target_service="lotus-risk",
        target_endpoint="/analytics/risk/concentration",
    )


