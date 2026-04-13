# tests/e2e/test_concentration_pipeline.py

import pytest

from .api_client import E2EApiClient
from .assertions import assert_legacy_endpoint_status
from .data_factory import unique_suffix

AS_OF_DATE = "2025-08-31"

@pytest.fixture(scope="module")
def setup_concentration_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the full
    concentration E2E test and waits for the pipeline to complete.
    """
    suffix = unique_suffix()
    portfolio_id = f"E2E_CONC_{suffix}"
    sec_a_id = f"SEC_CONC_A_{suffix}"
    sec_b_id = f"SEC_CONC_B_{suffix}"
    sec_c_id = f"SEC_CONC_C_{suffix}"

    # 1. Ingest prerequisite data
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": f"CONC_CIF_{suffix}",
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
                    "securityId": sec_a_id,
                    "name": "CONC_A",
                    "isin": f"ISIN_CONC_A_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                    "issuerId": f"ISS_XYZ_{suffix}",
                    "ultimateParentIssuerId": f"PARENT_XYZ_{suffix}",
                },
                {
                    "securityId": sec_b_id,
                    "name": "CONC_B",
                    "isin": f"ISIN_CONC_B_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                    "issuerId": f"ISS_XYZ_SUB_{suffix}",
                    "ultimateParentIssuerId": f"PARENT_XYZ_{suffix}",
                },
                {
                    "securityId": sec_c_id,
                    "name": "CONC_C",
                    "isin": f"ISIN_CONC_C_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                    "issuerId": f"ISS_ABC_{suffix}",
                    "ultimateParentIssuerId": f"PARENT_ABC_{suffix}",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/business-dates", {"business_dates": [{"businessDate": AS_OF_DATE}]}
    )

    # 2. Ingest transactions to create positions
    transactions = [
        {
            "transaction_id": f"{portfolio_id}_BUY_A",
            "portfolio_id": portfolio_id,
            "instrument_id": f"CONC_A_TICKER_{suffix}",
            "security_id": sec_a_id,
            "transaction_date": f"{AS_OF_DATE}T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 1,
            "gross_transaction_amount": 100,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_BUY_B",
            "portfolio_id": portfolio_id,
            "instrument_id": f"CONC_B_TICKER_{suffix}",
            "security_id": sec_b_id,
            "transaction_date": f"{AS_OF_DATE}T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 1,
            "gross_transaction_amount": 100,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_BUY_C",
            "portfolio_id": portfolio_id,
            "instrument_id": f"CONC_C_TICKER_{suffix}",
            "security_id": sec_c_id,
            "transaction_date": f"{AS_OF_DATE}T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 1,
            "gross_transaction_amount": 100,
            "trade_currency": "USD",
            "currency": "USD",
        },
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})

    # 3. Ingest market prices that will result in the desired weights
    prices = [
        {
            "securityId": sec_a_id,
            "priceDate": AS_OF_DATE,
            "price": 600.0,
            "currency": "USD",
        },  # 60,000
        {
            "securityId": sec_b_id,
            "priceDate": AS_OF_DATE,
            "price": 250.0,
            "currency": "USD",
        },  # 25,000
        {
            "securityId": sec_c_id,
            "priceDate": AS_OF_DATE,
            "price": 150.0,
            "currency": "USD",
        },  # 15,000
    ]  # Total Market Value = 100,000
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": prices})

    # 4. Poll until the final snapshot is valued for all positions
    poll_db_until(
        query="SELECT count(*) FROM daily_position_snapshots WHERE portfolio_id = :pid AND date = :date AND valuation_status = 'VALUED_CURRENT'",  # noqa: E501
        params={"pid": portfolio_id, "date": AS_OF_DATE},
        validation_func=lambda r: r is not None and r[0] == 3,
        timeout=120,
        fail_message=f"Pipeline did not value all 3 positions for {AS_OF_DATE}.",
    )
    return {"portfolio_id": portfolio_id}


def test_bulk_concentration_e2e(setup_concentration_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core concentration endpoint is hard-disabled and directs callers to lotus-risk.
    """
    portfolio_id = setup_concentration_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/concentration"
    request_payload = {
        "scope": {"as_of_date": AS_OF_DATE},
        "metrics": ["BULK"],
        "options": {"bulk_top_n": [2]},
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)
    assert_legacy_endpoint_status(response)


def test_issuer_concentration_e2e(setup_concentration_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core concentration endpoint is hard-disabled and directs callers to lotus-risk.
    """
    portfolio_id = setup_concentration_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/concentration"
    request_payload = {
        "scope": {"as_of_date": AS_OF_DATE},
        "metrics": ["ISSUER"],
        "options": {"issuer_top_n": 5},
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)
    assert_legacy_endpoint_status(response)
