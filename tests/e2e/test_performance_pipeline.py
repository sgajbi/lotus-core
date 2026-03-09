# tests/e2e/test_performance_pipeline.py
import uuid

import pytest

from tests.e2e.api_client import E2EApiClient
from tests.e2e.assertions import assert_legacy_endpoint_status


@pytest.fixture(scope="module")
def setup_performance_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests a full scenario for performance testing,
    including a BOD cashflow, and waits for the pipeline to generate the necessary
    time-series data.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_ADV_PERF_{suffix}"
    cash_security_id = f"CASH_USD_{suffix}"
    day1, day2 = "2025-03-10", "2025-03-11"

    # Ingest prerequisite data
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": "PERF_CIF",
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
                    "securityId": cash_security_id,
                    "name": "US Dollar",
                    "isin": f"CASH_USD_ISIN_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Cash",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/business-dates",
        {"business_dates": [{"businessDate": day1}, {"businessDate": day2}]},
    )

    # Seed a canonical cash position so valuation/timeseries materialize under
    # the current position-level modeling rules.
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": f"PERF_CASH_BUY_{suffix}",
                    "portfolio_id": portfolio_id,
                    "instrument_id": cash_security_id,
                    "security_id": cash_security_id,
                    "transaction_date": f"{day1}T08:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": 10000,
                    "price": 1,
                    "gross_transaction_amount": 10000,
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
                    "securityId": cash_security_id,
                    "priceDate": day1,
                    "price": 1.02,
                    "currency": "USD",
                },  # End of Day 1
                {
                    "securityId": cash_security_id,
                    "priceDate": day2,
                    "price": 1.05,
                    "currency": "USD",
                },  # End of Day 2
            ]
        },
    )

    # Poll until the timeseries for the final day is fully generated.
    poll_db_until(
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": portfolio_id, "date": day2},
        validation_func=lambda r: r is not None,
        timeout=180,
        fail_message="Pipeline did not generate portfolio_timeseries for the final day.",
    )
    return {"portfolio_id": portfolio_id}


def test_advanced_performance_api(setup_performance_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core performance endpoint is hard-disabled and directs
    callers to lotus-performance.
    """
    # ARRANGE
    portfolio_id = setup_performance_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/performance"

    # --- Manual Expected Calculations ---
    # Day 1 (Mar 10) RoR: (EOD_MV:10200 - BOD_MV:0 - BOD_CF:10000) / (BOD_MV:0 + BOD_CF:10000) = 2.0%  # noqa: E501
    # Day 2 (Mar 11) RoR: (EOD_MV:10500 - BOD_MV:10200) / BOD_MV:10200 = 2.941176%
    # Total Linked Return = ((1 + 0.02) * (1 + 0.02941176)) - 1 = 0.0500... => 5.0%

    request_payload = {
        "scope": {"as_of_date": "2025-03-11", "net_or_gross": "NET"},
        "periods": [
            {"name": "Month To Date", "type": "MTD"},
            {"name": "SpecificRange", "type": "EXPLICIT", "from": "2025-03-10", "to": "2025-03-11"},
        ],
        "options": {"include_cumulative": True, "include_annualized": False},
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)
    assert_legacy_endpoint_status(response)
