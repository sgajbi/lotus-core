# tests/e2e/test_valuation_pipeline.py
import uuid
from decimal import Decimal
from typing import Callable

import pytest

from .api_client import E2EApiClient
from .assertions import as_decimal


@pytest.fixture(scope="module")
def setup_valuation_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until: Callable):
    """
    A module-scoped fixture that ingests data for a simple valuation scenario,
    and waits for the calculation to complete by polling the database for the final state.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_VAL_PORT_{suffix}"
    security_id = f"SEC_E2E_VAL_{suffix}"
    tx_date = "2025-07-27"

    # 1. Ingest prerequisite data
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2025-01-01",
                    "risk_exposure": "Medium",
                    "investment_time_horizon": "Long",
                    "portfolio_type": "Advisory",
                    "booking_center_code": "NY",
                    "client_id": f"VAL_CIF_{suffix}",
                    "status": "ACTIVE",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "security_id": security_id,
                    "name": "Valuation Test Stock",
                    "isin": f"VAL12345_{suffix}",
                    "currency": "USD",
                    "product_type": "Equity",
                }
            ]
        },
    )

    # 2. Ingest transaction, market price, AND the business date to trigger the scheduler
    e2e_api_client.ingest(
        "/ingest/transactions",
        {
            "transactions": [
                {
                    "transaction_id": f"{portfolio_id}_BUY_01",
                    "portfolio_id": portfolio_id,
                    "instrument_id": f"E2E_VAL_{suffix}",
                    "security_id": security_id,
                    "transaction_date": f"{tx_date}T10:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": 10,
                    "price": 100.0,
                    "gross_transaction_amount": 1000.0,
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
                    "security_id": security_id,
                    "price_date": tx_date,
                    "price": 110.0,
                    "currency": "USD",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/business-dates",
        {"business_dates": [{"business_date": tx_date}]},
    )

    # 3. Poll the database until the daily_position_snapshot is fully valued.
    # This is a reliable indicator that the entire pipeline has completed.
    query = "SELECT valuation_status FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"  # noqa: E501
    params = {"pid": portfolio_id, "sid": security_id, "date": tx_date}
    def validation_func(r):
        return r is not None and r.valuation_status == "VALUED_CURRENT"

    poll_db_until(
        query=query,
        validation_func=validation_func,
        params=params,
        timeout=120,
        fail_message=f"Valuation for {security_id} on {tx_date} did not complete.",
    )

    return {"portfolio_id": portfolio_id, "security_id": security_id}


def test_full_valuation_pipeline(setup_valuation_data, e2e_api_client: E2EApiClient):
    """
    Tests the full pipeline from ingestion to position valuation, and verifies
    the final API response from the query service.
    """
    # ARRANGE
    portfolio_id = setup_valuation_data["portfolio_id"]

    # ACT: The pipeline has already run and been verified by the fixture; we just query the final state.  # noqa: E501
    api_response = e2e_api_client.query(f"/portfolios/{portfolio_id}/positions")
    response_data = api_response.json()

    # ASSERT
    assert len(response_data["positions"]) == 1
    position = response_data["positions"][0]
    valuation = position["valuation"]

    assert position["security_id"] == setup_valuation_data["security_id"]
    assert as_decimal(position["quantity"]) == Decimal("10")
    assert as_decimal(position["cost_basis"]) == Decimal("1000")

    assert as_decimal(valuation["market_price"]) == Decimal("110")
    # Expected market_value = 10 shares * 110/share = 1100
    assert as_decimal(valuation["market_value"]) == Decimal("1100")

    # Expected unrealized_gain_loss = 1100 (MV) - 1000 (Cost) = 100
    assert float(as_decimal(valuation["unrealized_gain_loss"])) == pytest.approx(100.0)
