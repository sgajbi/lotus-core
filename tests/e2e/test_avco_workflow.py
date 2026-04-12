# tests/e2e/test_avco_workflow.py
import uuid
from decimal import Decimal

import pytest

from .api_client import E2EApiClient
from .assertions import as_decimal


@pytest.fixture(scope="module")
def setup_avco_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests data for an Average Cost (AVCO) scenario
    and waits for the pipeline to complete.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_AVCO_PORT_{suffix}"
    security_id = f"SEC_AVCO_TEST_{suffix}"
    instrument_id = f"AVCO_{suffix}"
    sell_tx_id = f"{portfolio_id}_SELL_01"

    # 1. Ingest prerequisite data, explicitly setting the cost basis method to AVCO
    e2e_api_client.ingest(
        "/ingest/portfolios",
        {
            "portfolios": [
                {
                    "portfolioId": portfolio_id,
                    "baseCurrency": "USD",
                    "openDate": "2025-01-01",
                    "cifId": f"AVCO_CIF_{suffix}",
                    "status": "ACTIVE",
                    "riskExposure": "High",
                    "investmentTimeHorizon": "Long",
                    "portfolioType": "Discretionary",
                    "bookingCenter": "SG",
                    "costBasisMethod": "AVCO",
                }
            ]
        },
    )
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "securityId": security_id,
                    "name": "AVCO Test Stock",
                    "isin": f"AVCO123_{suffix}",
                    "instrumentCurrency": "USD",
                    "productType": "Equity",
                }
            ]
        },
    )

    # 2. Ingest transactions: two buys at different prices, then a sell
    transactions = [
        {
            "transaction_id": f"{portfolio_id}_BUY_01",
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
            "security_id": security_id,
            "transaction_date": "2025-08-01T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 10.0,
            "gross_transaction_amount": 1000.0,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": f"{portfolio_id}_BUY_02",
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
            "security_id": security_id,
            "transaction_date": "2025-08-05T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 12.0,
            "gross_transaction_amount": 1200.0,
            "trade_currency": "USD",
            "currency": "USD",
        },
        {
            "transaction_id": sell_tx_id,
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
            "security_id": security_id,
            "transaction_date": "2025-08-10T10:00:00Z",
            "transaction_type": "SELL",
            "quantity": 50,
            "price": 15.0,
            "gross_transaction_amount": 750.0,
            "trade_currency": "USD",
            "currency": "USD",
        },
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})

    # 3. Poll the query service until the final transaction is fully processed and has a P&L figure
    poll_url = f"/portfolios/{portfolio_id}/transactions"
    def validation_func(data):
        return (
            data.get("transactions")
            and len(data["transactions"]) == 3
            and next(
                (t for t in data["transactions"] if t["transaction_id"] == sell_tx_id),
                {},
            ).get("realized_gain_loss")
            is not None
        )
    e2e_api_client.poll_for_data(poll_url, validation_func, timeout=90)

    return {"portfolio_id": portfolio_id, "sell_tx_id": sell_tx_id}


def test_avco_realized_pnl(setup_avco_data, e2e_api_client: E2EApiClient):
    """
    Verifies the realized P&L on the SELL transaction is calculated correctly
    according to the Average Cost methodology.
    """
    # ARRANGE
    portfolio_id = setup_avco_data["portfolio_id"]
    tx_url = f"/portfolios/{portfolio_id}/transactions"

    # ACT
    response = e2e_api_client.query(tx_url)
    tx_data = response.json()
    sell_tx = next(
        t for t in tx_data["transactions"] if t["transaction_id"] == setup_avco_data["sell_tx_id"]
    )

    # ASSERT
    # After the two buys, the position is 200 shares with a total cost of $2200 ($1000 + $1200).
    # The average cost per share is $11 ($2200 / 200).
    # COGS for the sale of 50 shares = 50 * $11 = $550.
    # Proceeds from the sale = 50 * $15 = $750.
    # Realized P&L = $750 (Proceeds) - $550 (COGS) = $200.
    assert as_decimal(sell_tx["realized_gain_loss"]) == Decimal("200")
