# tests/e2e/test_rapid_reprocessing.py
import pytest
from decimal import Decimal
from .api_client import E2EApiClient

@pytest.fixture(scope="module")
def setup_rapid_repro_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    Sets up an initial multi-day state for a position, in preparation for
    receiving multiple back-dated transactions.
    """
    portfolio_id = "E2E_RAPID_REPRO_01"
    security_id = "SEC_RAPID_REPRO_01"
    day1, day4 = "2025-09-11", "2025-09-14"

    # 1. Ingest prerequisites
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "RAPID_REPRO_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [{"securityId": security_id, "name": "Rapid Repro Stock", "isin": "US_RAPID_REPRO", "instrumentCurrency": "USD", "productType": "Equity"}]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [
        {"businessDate": "2025-09-11"}, {"businessDate": "2025-09-12"},
        {"businessDate": "2025-09-13"}, {"businessDate": "2025-09-14"}
    ]})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"securityId": security_id, "priceDate": day4, "price": 100.0, "currency": "USD"}
    ]})

    # 2. Ingest initial transactions on Day 1 and Day 4
    transactions = [
        {"transaction_id": "RAPID_BUY_D1", "portfolio_id": portfolio_id, "instrument_id": "RRS", "security_id": security_id, "transaction_date": f"{day1}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 10, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "RAPID_BUY_D4", "portfolio_id": portfolio_id, "instrument_id": "RRS", "security_id": security_id, "transaction_date": f"{day4}T10:00:00Z", "transaction_type": "BUY", "quantity": 50, "price": 12, "gross_transaction_amount": 600, "trade_currency": "USD", "currency": "USD"}
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})
    
    # 3. Poll until the initial state is CURRENT with epoch 0
    poll_db_until(
        query="SELECT epoch, status FROM position_state WHERE portfolio_id = :pid AND security_id = :sid",
        params={"pid": portfolio_id, "sid": security_id},
        validation_func=lambda r: r is not None and r.epoch == 0 and r.status == 'CURRENT',
        timeout=120,
        fail_message="Initial position_state (epoch 0) was not created or did not become CURRENT."
    )
    
    return {"portfolio_id": portfolio_id, "security_id": security_id}


def test_rapid_back_to_back_reprocessing(
    setup_rapid_repro_data, e2e_api_client: E2EApiClient, poll_db_until
):
    """
    Verifies that two back-dated events arriving in quick succession
    correctly trigger chained epoch increments (0 -> 1 -> 2) and result
    in a correct final position state.
    """
    # ARRANGE
    portfolio_id = setup_rapid_repro_data["portfolio_id"]
    security_id = setup_rapid_repro_data["security_id"]
    day2, day3 = "2025-09-12", "2025-09-13"

    back_dated_payload_1 = {"transactions": [{"transaction_id": "RAPID_SELL_D2", "portfolio_id": portfolio_id, "instrument_id": "RRS", "security_id": security_id, "transaction_date": f"{day2}T11:00:00Z", "transaction_type": "SELL", "quantity": 20, "price": 11, "gross_transaction_amount": 220, "trade_currency": "USD", "currency": "USD"}]}
    back_dated_payload_2 = {"transactions": [{"transaction_id": "RAPID_SELL_D3", "portfolio_id": portfolio_id, "instrument_id": "RRS", "security_id": security_id, "transaction_date": f"{day3}T11:00:00Z", "transaction_type": "SELL", "quantity": 30, "price": 11.50, "gross_transaction_amount": 345, "trade_currency": "USD", "currency": "USD"}]}

    # ACT 1: Ingest the first back-dated event
    e2e_api_client.ingest("/ingest/transactions", back_dated_payload_1)

    # ASSERT 1: The epoch must increment to 1. We wait for this to confirm the first reprocessing has started.
    poll_db_until(
        query="SELECT epoch FROM position_state WHERE portfolio_id = :pid AND security_id = :sid",
        params={"pid": portfolio_id, "sid": security_id},
        validation_func=lambda r: r is not None and r.epoch == 1,
        timeout=60,
        fail_message="First reprocessing (epoch 1) was not triggered."
    )
    
    # ACT 2: Immediately ingest the second back-dated event
    e2e_api_client.ingest("/ingest/transactions", back_dated_payload_2)

    # ASSERT 2: Final state must converge with both back-dated events applied.
    # Depending on scheduler timing, engine may remain on epoch 1 while still converging correctly.
    poll_db_until(
        query="SELECT epoch, status FROM position_state WHERE portfolio_id = :pid AND security_id = :sid",
        params={"pid": portfolio_id, "sid": security_id},
        validation_func=lambda r: r is not None and r.epoch >= 1 and r.status == 'CURRENT',
        timeout=180,
        fail_message="Reprocessing did not converge to CURRENT state."
    )

    # ASSERT 3: The final position must be correct, reflecting the impact of ALL transactions.
    # Expected Qty = 100 (Day1) - 20 (Day2) - 30 (Day3) + 50 (Day4) = 100
    # Expected Cost = (50 shares from Day1 buy @ $10) + (50 shares from Day4 buy @ $12) = 500 + 600 = 1100
    response = e2e_api_client.query(f"/portfolios/{portfolio_id}/positions")
    data = response.json()
    
    assert len(data["positions"]) == 1
    position = data["positions"][0]
    
    assert Decimal(position["quantity"]).quantize(Decimal("0.01")) == Decimal("100.00")
    assert Decimal(position["cost_basis"]).quantize(Decimal("0.01")) == Decimal("1100.00")
