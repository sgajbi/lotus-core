# tests/e2e/test_summary_pipeline.py
import uuid

import pytest

from .api_client import E2EApiClient
from .assertions import assert_legacy_endpoint_status

AS_OF_DATE = "2025-08-29"
PERIOD_START = "2025-08-01"


@pytest.fixture(scope="module")
def setup_summary_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the summary E2E test.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_SUM_PORT_{suffix}"
    msft_id = f"SEC_MSFT_SUM_{suffix}"
    ibm_id = f"SEC_IBM_SUM_{suffix}"
    cash_id = f"CASH_USD_{suffix}"

    # 1. Ingest prerequisite data
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": f"SUM_CIF_{suffix}",
                    "status": "ACTIVE",
                    "riskExposure": "a",
                    "investmentTimeHorizon": "b",
                    "portfolioType": "c",
                    "bookingCenter": "d",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "securityId": cash_id,
                    "name": "US Dollar",
                    "isin": f"CASH_USD_ISIN_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Cash",
                    "assetClass": "Cash",
                },
                {
                    "securityId": msft_id,
                    "name": "Microsoft",
                    "isin": f"US_MSFT_SUM_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                    "sector": "Technology",
                    "countryOfRisk": "US",
                },
                {
                    "securityId": ibm_id,
                    "name": "IBM",
                    "isin": f"US_IBM_SUM_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                    "sector": "Technology",
                    "countryOfRisk": "US",
                },
            ]
        },
    )
    all_dates = [
        "2025-07-31",
        PERIOD_START,
        "2025-08-05",
        "2025-08-10",
        "2025-08-15",
        "2025-08-20",
        "2025-08-22",
        "2025-08-26",
        "2025-08-27",
        AS_OF_DATE,
    ]
    e2e_api_client.ingest(
        "/ingest/business-dates", {"business_dates": [{"businessDate": d} for d in all_dates]}
    )

    # 2. Ingest a comprehensive list of transactions
    transactions = [
        {
            "transaction_id": f"{portfolio_id}_DEPOSIT_01",
            "portfolio_id": portfolio_id,
            "instrument_id": "CASH",
            "security_id": cash_id,
            "transaction_date": f"{PERIOD_START}T09:00:00Z",
            "transaction_type": "DEPOSIT",
            "quantity": 1000000,
            "price": 1,
            "gross_transaction_amount": 1000000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_BUY_MSFT",
            "portfolio_id": portfolio_id,
            "instrument_id": "MSFT",
            "security_id": msft_id,
            "transaction_date": "2025-08-05T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 1000,
            "price": 300,
            "gross_transaction_amount": 300000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_CASH_SETTLE_1",
            "portfolio_id": portfolio_id,
            "instrument_id": "CASH",
            "security_id": cash_id,
            "transaction_date": "2025-08-05T10:00:00Z",
            "transaction_type": "SELL",
            "quantity": 300000,
            "price": 1,
            "gross_transaction_amount": 300000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_TRANSFER_IN_IBM",
            "portfolio_id": portfolio_id,
            "instrument_id": "IBM",
            "security_id": ibm_id,
            "transaction_date": "2025-08-10T10:00:00Z",
            "transaction_type": "TRANSFER_IN",
            "quantity": 100,
            "price": 150,
            "gross_transaction_amount": 15000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_SELL_MSFT",
            "portfolio_id": portfolio_id,
            "instrument_id": "MSFT",
            "security_id": msft_id,
            "transaction_date": "2025-08-15T10:00:00Z",
            "transaction_type": "SELL",
            "quantity": 200,
            "price": 320,
            "gross_transaction_amount": 64000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_CASH_SETTLE_2",
            "portfolio_id": portfolio_id,
            "instrument_id": "CASH",
            "security_id": cash_id,
            "transaction_date": "2025-08-15T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 64000,
            "price": 1,
            "gross_transaction_amount": 64000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_FEE_01",
            "portfolio_id": portfolio_id,
            "instrument_id": "CASH",
            "security_id": cash_id,
            "transaction_date": "2025-08-20T10:00:00Z",
            "transaction_type": "FEE",
            "quantity": 1,
            "price": 50,
            "gross_transaction_amount": 50,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_DIVIDEND_MSFT",
            "portfolio_id": portfolio_id,
            "instrument_id": "MSFT",
            "security_id": msft_id,
            "transaction_date": "2025-08-22T10:00:00Z",
            "transaction_type": "DIVIDEND",
            "quantity": 0,
            "price": 0,
            "gross_transaction_amount": 400,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_CASH_SETTLE_3",
            "portfolio_id": portfolio_id,
            "instrument_id": "CASH",
            "security_id": cash_id,
            "transaction_date": "2025-08-22T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 400,
            "price": 1,
            "gross_transaction_amount": 400,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_WITHDRAWAL_01",
            "portfolio_id": portfolio_id,
            "instrument_id": "CASH",
            "security_id": cash_id,
            "transaction_date": "2025-08-26T10:00:00Z",
            "transaction_type": "WITHDRAWAL",
            "quantity": 10000,
            "price": 1,
            "gross_transaction_amount": 10000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_TRANSFER_OUT_MSFT",
            "portfolio_id": portfolio_id,
            "instrument_id": "MSFT",
            "security_id": msft_id,
            "transaction_date": "2025-08-27T10:00:00Z",
            "transaction_type": "TRANSFER_OUT",
            "quantity": 50,
            "price": 330,
            "gross_transaction_amount": 16500,
            "trade_currency": "USD",
            "currency": "USD",
        },
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})

    # 3. Ingest market prices
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {"securityId": msft_id, "priceDate": AS_OF_DATE, "price": 340.0, "currency": "USD"},
                {"securityId": ibm_id, "priceDate": AS_OF_DATE, "price": 155.0, "currency": "USD"},
                {"securityId": cash_id, "priceDate": AS_OF_DATE, "price": 1.0, "currency": "USD"},
            ]
        },
    )

    # 4. Poll until the final snapshot is valued
    poll_db_until(
        query="SELECT count(*) FROM daily_position_snapshots WHERE portfolio_id = :pid AND date = :date AND valuation_status = 'VALUED_CURRENT'",  # noqa: E501
        params={"pid": portfolio_id, "date": AS_OF_DATE},
        validation_func=lambda r: r is not None and r[0] >= 3,
        timeout=180,
        fail_message=f"Pipeline did not value all 3 positions for {AS_OF_DATE}.",
    )
    return {"portfolio_id": portfolio_id}


def test_portfolio_summary_endpoint(setup_summary_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core summary endpoint is hard-disabled and directs callers to lotus-report.
    """
    portfolio_id = setup_summary_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/summary"
    request_payload = {
        "as_of_date": AS_OF_DATE,
        "period": {"type": "EXPLICIT", "from": PERIOD_START, "to": AS_OF_DATE},
        "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY", "ALLOCATION"],
        "allocation_dimensions": ["ASSET_CLASS", "SECTOR", "COUNTRY_OF_RISK"],
    }

    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)
    assert_legacy_endpoint_status(
        response,
        target_service="lotus-report",
        target_endpoint="/reports/portfolios/{portfolio_id}/summary",
    )
