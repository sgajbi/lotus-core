# tests/e2e/test_timeseries_pipeline.py
import pytest
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date
from .api_client import E2EApiClient

@pytest.fixture(scope="module")
def setup_timeseries_data(clean_db_module, db_engine, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture to clean the DB, ingest all necessary data once,
    and wait for the pipeline to complete by polling for specific, correct values.
    """
    portfolio_id = "E2E_TS_PORT"
    
    # Ingest all base data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolio_id": portfolio_id, "base_currency": "USD", "open_date": "2025-01-01", "risk_exposure": "High", "investment_time_horizon": "Long", "portfolio_type": "Discretionary", "booking_center_code": "SG", "client_id": "TS_CIF", "status": "Active"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [
        {"security_id": "SEC_EUR_STOCK", "name": "Euro Stock", "isin": "EU123", "currency": "EUR", "product_type": "Equity"},
        {"security_id": "CASH", "name": "US Dollar", "isin": "USD_CASH", "currency": "USD", "product_type": "Cash"}
    ]})
    e2e_api_client.ingest("/ingest/fx-rates", {"fx_rates": [{"from_currency": "EUR", "to_currency": "USD", "rate_date": "2025-07-28", "rate": "1.1"}, {"from_currency": "EUR", "to_currency": "USD", "rate_date": "2025-07-29", "rate": "1.2"}]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"business_date": "2025-07-28"}, {"business_date": "2025-07-29"}]})

    # --- Day 1 (2025-07-28) ---
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [{"transaction_id": "TS_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "EUR_STOCK", "security_id": "SEC_EUR_STOCK", "transaction_date": "2025-07-28T00:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 50, "gross_transaction_amount": 5000, "trade_currency": "EUR", "currency": "EUR"}]})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [{"security_id": "SEC_EUR_STOCK", "price_date": "2025-07-28", "price": 52, "currency": "EUR"}]})
    
    # --- Day 2 (2025-07-29) ---
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [{"transaction_id": "TS_FEE_01", "portfolio_id": portfolio_id, "instrument_id": "CASH", "security_id": "CASH", "transaction_date": "2025-07-29T00:00:00Z", "transaction_type": "FEE", "quantity": 1, "price": 25, "gross_transaction_amount": 25, "trade_currency": "USD", "currency": "USD"}]})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"security_id": "SEC_EUR_STOCK", "price_date": "2025-07-29", "price": 55, "currency": "EUR"},
        {"security_id": "CASH", "price_date": "2025-07-29", "price": 1, "currency": "USD"}
    ]})
    
    # Poll for the final value of Day 2 to ensure the full pipeline is complete
    poll_db_until(
        query="SELECT eod_market_value FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": portfolio_id, "date": date(2025, 7, 29)},
        validation_func=lambda r: r is not None and r.eod_market_value == Decimal("6575.0000000000"),
        timeout=180,
        fail_message="Pipeline did not generate correct portfolio_timeseries for Day 2."
    )
    
    return {"db_engine": db_engine}

def test_timeseries_day_1(setup_timeseries_data):
    """Verify the portfolio time series record for the first day."""
    with Session(setup_timeseries_data["db_engine"]) as session:
        query = text("SELECT bod_market_value, bod_cashflow, eod_cashflow, eod_market_value, fees FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :date")
        result = session.execute(query, {"portfolio_id": "E2E_TS_PORT", "date": "2025-07-28"}).fetchone()

    assert result is not None, "Time series record for day 1 was not found."
    bod_mv, bod_cf, eod_cf, eod_mv, fees = result
    
    # On Day 1, BOD values are 0. The BUY is a BOD cashflow for the position, but not the portfolio.
    # EOD MV (local) = 100 shares * 52 EUR = 5200 EUR.
    # EOD MV (base) = 5200 EUR * 1.1 FX = 5720 USD.
    assert bod_mv == Decimal("0.0000000000")
    assert bod_cf == Decimal("0.0000000000")
    assert eod_cf == Decimal("0.0000000000")
    assert eod_mv == Decimal("5720.0000000000")
    assert fees == Decimal("0.0000000000")

def test_timeseries_day_2(setup_timeseries_data):
    """Verify the portfolio time series record for the second day."""
    with Session(setup_timeseries_data["db_engine"]) as session:
        query = text("SELECT bod_market_value, bod_cashflow, eod_cashflow, eod_market_value, fees FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :date")
        result = session.execute(query, {"portfolio_id": "E2E_TS_PORT", "date": "2025-07-29"}).fetchone()

    assert result is not None, "Time series record for day 2 was not found."
    bod_mv, bod_cf, eod_cf, eod_mv, fees = result

    # BOD MV = EOD MV from Day 1 = 5720 USD.
    # A $25 FEE is an EOD portfolio-level cashflow.
    # EOD MV (local) = 100 shares * 55 EUR = 5500 EUR.
    # EOD MV (base) = 5500 EUR * 1.2 FX = 6600 USD. Cash position is now -25 USD. Total = 6575 USD.
    assert bod_mv == Decimal("5720.0000000000")
    assert bod_cf == Decimal("0.0000000000")
    assert eod_cf == Decimal("-25.0000000000")
    assert eod_mv == Decimal("6575.0000000000")
    assert fees == Decimal("25.0000000000")

def test_position_timeseries_day_2(setup_timeseries_data):
    """Verify the individual position time series records for the second day."""
    with Session(setup_timeseries_data["db_engine"]) as session:
        query = text("SELECT security_id, eod_market_value, bod_cashflow_portfolio, eod_cashflow_portfolio FROM position_timeseries WHERE portfolio_id = :portfolio_id AND date = :date")
        results = session.execute(query, {"portfolio_id": "E2E_TS_PORT", "date": "2025-07-29"}).fetchall()

    assert len(results) >= 2, "Expected at least two position time series records for day 2"
    
    records = {row.security_id: row for row in results}
    
    # Verify the stock position
    stock_pos = records.get("SEC_EUR_STOCK")
    assert stock_pos is not None
    assert stock_pos.eod_market_value == Decimal("5500.0000000000") # 100 * 55 EUR (local currency)
    assert stock_pos.bod_cashflow_portfolio == Decimal("0.0000000000")
    assert stock_pos.eod_cashflow_portfolio == Decimal("0.0000000000")

    # Verify the cash position
    cash_pos = records.get("CASH")
    assert cash_pos is not None
    assert cash_pos.eod_market_value == Decimal("-25.0000000000")
    assert cash_pos.bod_cashflow_portfolio == Decimal("0.0000000000")
    assert cash_pos.eod_cashflow_portfolio == Decimal("-25.0000000000")