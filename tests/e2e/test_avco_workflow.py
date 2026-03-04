# tests/e2e/test_avco_workflow.py
import pytest
from decimal import Decimal
from .api_client import E2EApiClient
from .assertions import assert_decimal_approx

@pytest.fixture(scope="module")
def setup_avco_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests data for an Average Cost (AVCO) scenario
    and waits for the pipeline to complete.
    """
    portfolio_id = "E2E_AVCO_PORT_01"
    security_id = "SEC_AVCO_TEST"
    
    # 1. Ingest prerequisite data, explicitly setting the cost basis method to AVCO
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{
        "portfolio_id": portfolio_id, "base_currency": "USD", "open_date": "2025-01-01",
        "client_id": "AVCO_CIF", "status": "ACTIVE", "risk_exposure": "High",
        "investment_time_horizon": "Long", "portfolio_type": "Discretionary", "booking_center_code": "SG",
        "cost_basis_method": "AVCO"
    }]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [{"security_id": security_id, "name": "AVCO Test Stock", "isin": "AVCO123", "currency": "USD", "product_type": "Equity"}]})

    # 2. Ingest transactions: two buys at different prices, then a sell
    transactions = [
        {"transaction_id": "AVCO_BUY_1", "portfolio_id": portfolio_id, "instrument_id": "AVCO", "security_id": security_id, "transaction_date": "2025-08-01T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 10.0, "gross_transaction_amount": 1000.0, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "AVCO_BUY_2", "portfolio_id": portfolio_id, "instrument_id": "AVCO", "security_id": security_id, "transaction_date": "2025-08-05T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 12.0, "gross_transaction_amount": 1200.0, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "AVCO_SELL_1", "portfolio_id": portfolio_id, "instrument_id": "AVCO", "security_id": security_id, "transaction_date": "2025-08-10T10:00:00Z", "transaction_type": "SELL", "quantity": 50, "price": 15.0, "gross_transaction_amount": 750.0, "trade_currency": "USD", "currency": "USD"},
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})

    # 3. Poll the query service until the final transaction is fully processed and has a P&L figure
    poll_url = f"/portfolios/{portfolio_id}/transactions"
    validation_func = lambda data: (
        data.get("transactions") and len(data["transactions"]) == 3 and
        next((t for t in data["transactions"] if t["transaction_id"] == "AVCO_SELL_1"), {}).get("realized_gain_loss") is not None
    )
    e2e_api_client.poll_for_data(poll_url, validation_func, timeout=90)
    
    return {"portfolio_id": portfolio_id}

def test_avco_realized_pnl(setup_avco_data, e2e_api_client: E2EApiClient):
    """
    Verifies the realized P&L on the SELL transaction is calculated correctly
    according to the Average Cost methodology.
    """
    # ARRANGE
    portfolio_id = setup_avco_data["portfolio_id"]
    tx_url = f'/portfolios/{portfolio_id}/transactions'

    # ACT
    response = e2e_api_client.query(tx_url)
    tx_data = response.json()
    sell_tx = next(t for t in tx_data["transactions"] if t["transaction_id"] == "AVCO_SELL_1")

    # ASSERT
    # After the two buys, the position is 200 shares with a total cost of $2200 ($1000 + $1200).
    # The average cost per share is $11 ($2200 / 200).
    # COGS for the sale of 50 shares = 50 * $11 = $550.
    # Proceeds from the sale = 50 * $15 = $750.
    # Realized P&L = $750 (Proceeds) - $550 (COGS) = $200.
    assert_decimal_approx(sell_tx["realized_gain_loss"], 200.0)
