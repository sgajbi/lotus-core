# tests/e2e/test_review_pipeline.py
import uuid

import pytest

from .api_client import E2EApiClient
from .assertions import assert_legacy_endpoint_status

AS_OF_DATE = "2025-08-30"


@pytest.fixture(scope="module")
def setup_review_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the full
    portfolio review E2E test.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_REVIEW_{suffix}"
    cash_id = f"CASH_USD_{suffix}"
    equity_id = f"SEC_AAPL_{suffix}"
    bond_id = f"SEC_BOND_{suffix}"

    # 1. Ingest prerequisite data
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": f"REVIEW_CIF_{suffix}",
                    "status": "ACTIVE",
                    "riskExposure": "Growth",
                    "investmentTimeHorizon": "b",
                    "portfolioType": "Discretionary",
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
                    "securityId": equity_id,
                    "name": "Apple Inc.",
                    "isin": f"US_AAPL_REVIEW_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                    "assetClass": "Equity",
                },
                {
                    "securityId": bond_id,
                    "name": "US Treasury Bond",
                    "isin": f"US_BOND_REVIEW_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Bond",
                    "assetClass": "Fixed Income",
                },
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/business-dates",
        {
            "business_dates": [
                {"businessDate": "2025-08-20"},
                {"businessDate": "2025-08-25"},
                {"businessDate": AS_OF_DATE},
            ]
        },
    )

    # 2. Ingest transactions to build a history
    transactions = [
        {
            "transaction_id": f"{portfolio_id}_DEPOSIT_01",
            "portfolio_id": portfolio_id,
            "instrument_id": cash_id,
            "security_id": cash_id,
            "transaction_date": "2025-08-20T09:00:00Z",
            "transaction_type": "DEPOSIT",
            "quantity": 100000,
            "price": 1,
            "gross_transaction_amount": 100000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        # Apple Purchase
        {
            "transaction_id": f"{portfolio_id}_BUY_AAPL",
            "portfolio_id": portfolio_id,
            "instrument_id": equity_id,
            "security_id": equity_id,
            "transaction_date": "2025-08-20T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 150,
            "gross_transaction_amount": 15000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_CASH_SETTLE_AAPL",
            "portfolio_id": portfolio_id,
            "instrument_id": cash_id,
            "security_id": cash_id,
            "transaction_date": "2025-08-20T10:00:00Z",
            "transaction_type": "SELL",
            "quantity": 15000,
            "price": 1,
            "gross_transaction_amount": 15000,
            "trade_currency": "USD",
            "currency": "USD",
        },
        # Bond Purchase
        {
            "transaction_id": f"{portfolio_id}_BUY_BOND",
            "portfolio_id": portfolio_id,
            "instrument_id": bond_id,
            "security_id": bond_id,
            "transaction_date": "2025-08-20T11:00:00Z",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 980,
            "gross_transaction_amount": 9800,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_CASH_SETTLE_BOND",
            "portfolio_id": portfolio_id,
            "instrument_id": cash_id,
            "security_id": cash_id,
            "transaction_date": "2025-08-20T11:00:00Z",
            "transaction_type": "SELL",
            "quantity": 9800,
            "price": 1,
            "gross_transaction_amount": 9800,
            "trade_currency": "USD",
            "currency": "USD",
        },
        # Dividend Payment
        {
            "transaction_id": f"{portfolio_id}_DIV_AAPL",
            "portfolio_id": portfolio_id,
            "instrument_id": equity_id,
            "security_id": equity_id,
            "transaction_date": "2025-08-25T10:00:00Z",
            "transaction_type": "DIVIDEND",
            "quantity": 0,
            "price": 0,
            "gross_transaction_amount": 120,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_CASH_SETTLE_DIV",
            "portfolio_id": portfolio_id,
            "instrument_id": cash_id,
            "security_id": cash_id,
            "transaction_date": "2025-08-25T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 120,
            "price": 1,
            "gross_transaction_amount": 120,
            "trade_currency": "USD",
            "currency": "USD",
        },
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})

    # 3. Ingest market prices for valuation
    e2e_api_client.ingest(
        "/ingest/market-prices",
        {
            "market_prices": [
                {
                    "securityId": equity_id,
                    "priceDate": AS_OF_DATE,
                    "price": 160.0,
                    "currency": "USD",
                },
                {
                    "securityId": bond_id,
                    "priceDate": AS_OF_DATE,
                    "price": 995.0,
                    "currency": "USD",
                },
                {
                    "securityId": cash_id,
                    "priceDate": AS_OF_DATE,
                    "price": 1.0,
                    "currency": "USD",
                },
            ]
        },
    )

    # 4. Poll until positions are fully queryable with valuation payload
    e2e_api_client.poll_for_data(
        f"/portfolios/{portfolio_id}/positions",
        lambda data: (
            data.get("positions")
            and any(p.get("security_id") == equity_id for p in data["positions"])
            and all(p.get("valuation") for p in data["positions"])
        ),
        timeout=180,
        fail_message=f"Pipeline did not generate queryable valued positions for {AS_OF_DATE}.",
    )
    return {"portfolio_id": portfolio_id}


def test_portfolio_review_endpoint(setup_review_data, e2e_api_client: E2EApiClient):
    """
    Verifies lotus-core review endpoint is hard-disabled and directs callers to lotus-report.
    """
    portfolio_id = setup_review_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/review"
    request_payload = {
        "as_of_date": AS_OF_DATE,
        "sections": ["OVERVIEW", "HOLDINGS", "TRANSACTIONS", "PERFORMANCE", "RISK_ANALYTICS"],
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)

    # ASSERT
    assert_legacy_endpoint_status(
        response,
        target_service="lotus-report",
        target_endpoint="/reports/portfolios/{portfolio_id}/review",
    )


def test_portfolio_review_for_empty_portfolio(clean_db, e2e_api_client: E2EApiClient):
    """
    Verifies empty-portfolio calls also receive 410 migration guidance.
    """
    # ARRANGE
    empty_portfolio_id = f"E2E_REVIEW_EMPTY_{uuid.uuid4().hex[:8].upper()}"
    as_of = "2025-08-31"

    # 1. Ingest only the portfolio and a business date
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": empty_portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": f"REVIEW_EMPTY_CIF_{empty_portfolio_id}",
                    "status": "ACTIVE",
                    "riskExposure": "Balanced",
                    "investmentTimeHorizon": "c",
                    "portfolioType": "d",
                    "bookingCenter": "e",
                }
            ]
        },
    )
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": as_of}]})

    # 2. Wait for the portfolio to be queryable
    e2e_api_client.poll_for_data(
        f"/portfolios?portfolio_id={empty_portfolio_id}",
        lambda data: data and data.get("portfolios") and len(data["portfolios"]) == 1,
    )

    # 3. Define the request for the review endpoint
    api_url = f"/portfolios/{empty_portfolio_id}/review"
    request_payload = {
        "as_of_date": as_of,
        "sections": ["OVERVIEW", "HOLDINGS", "TRANSACTIONS", "PERFORMANCE", "RISK_ANALYTICS"],
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload, raise_for_status=False)

    # ASSERT
    assert_legacy_endpoint_status(
        response,
        target_service="lotus-report",
        target_endpoint="/reports/portfolios/{portfolio_id}/review",
    )
