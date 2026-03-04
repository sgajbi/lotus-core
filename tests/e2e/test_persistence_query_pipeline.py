# tests/e2e/test_persistence_query_pipeline.py
import pytest
from datetime import date
from .api_client import E2EApiClient

@pytest.fixture(scope="module")
def setup_persistence_data(clean_db_module, e2e_api_client: E2EApiClient):
    """
    A module-scoped fixture that ingests a comprehensive set of data and waits for it all to be queryable.
    """
    # Define all identifiers
    portfolio_id = "E2E_PQ_PORT_01"
    security_id = "SEC_PQ_INST_01"
    transaction_id = "TXN_PQ_01"
    price_date = date.today().isoformat()
    
    # Ingest one of each entity type using the new client
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolio_id": portfolio_id, "base_currency": "SGD", "open_date": "2024-01-01", "client_id": "CIF_PQ_1", "status": "ACTIVE", "risk_exposure":"a", "investment_time_horizon":"b", "portfolio_type":"c", "booking_center_code":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [
        {"security_id": security_id, "name": "Test Instrument PQ", "isin": f"ISIN_{security_id}", "currency": "USD", "product_type": "Equity"},
        {"security_id": "SEC_NO_PRICE", "name": "Unpriced Instrument", "isin": "ISIN_NO_PRICE", "currency": "USD", "product_type": "Equity"}
    ]})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [{"security_id": security_id, "price_date": price_date, "price": 123.45, "currency": "HKD"}]})
    e2e_api_client.ingest("/ingest/fx-rates", {"fx_rates": [
        {"from_currency": "USD", "to_currency": "EUR", "rate_date": price_date, "rate": 0.95},
        {"from_currency": "USD", "to_currency": "SGD", "rate_date": price_date, "rate": 1.35}
    ]})
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [{"transaction_id": transaction_id, "portfolio_id": portfolio_id, "instrument_id": "TEST", "security_id": security_id, "transaction_date": f"{price_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 10, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"}]})

    # Poll all endpoints to ensure data is ready before tests run
    e2e_api_client.poll_for_data(f"/portfolios?portfolio_id={portfolio_id}", lambda data: data.get("portfolios") and len(data["portfolios"]) == 1)
    e2e_api_client.poll_for_data(f"/instruments?security_id={security_id}", lambda data: data.get("instruments") and len(data["instruments"]) == 1)
    e2e_api_client.poll_for_data(f"/prices?security_id={security_id}", lambda data: data.get("prices") and len(data["prices"]) == 1)
    e2e_api_client.poll_for_data(f"/fx-rates?from_currency=USD&to_currency=EUR", lambda data: data.get("rates") and len(data["rates"]) == 1)
    e2e_api_client.poll_for_data(f"/portfolios/{portfolio_id}/transactions", lambda data: data.get("transactions") and len(data["transactions"]) == 1)

    return {"portfolio_id": portfolio_id, "security_id": security_id, "transaction_id": transaction_id, "price_date": price_date}

def test_portfolio_query(setup_persistence_data, e2e_api_client: E2EApiClient):
    """Tests that the ingested portfolio can be queried correctly."""
    api_response = e2e_api_client.query(f"/portfolios?portfolio_id={setup_persistence_data['portfolio_id']}")
    data = api_response.json()["portfolios"][0]
    assert data["portfolio_id"] == setup_persistence_data["portfolio_id"]
    assert data["base_currency"] == "SGD"

def test_instrument_query(setup_persistence_data, e2e_api_client: E2EApiClient):
    """Tests that the ingested instrument can be queried correctly."""
    api_response = e2e_api_client.query(f"/instruments?security_id={setup_persistence_data['security_id']}")
    data = api_response.json()["instruments"][0]
    assert data["security_id"] == setup_persistence_data["security_id"]
    assert data["name"] == "Test Instrument PQ"

def test_market_price_query(setup_persistence_data, e2e_api_client: E2EApiClient):
    """Tests that the ingested market price can be queried correctly."""
    api_response = e2e_api_client.query(f"/prices?security_id={setup_persistence_data['security_id']}")
    data = api_response.json()["prices"][0]
    assert data["price_date"] == setup_persistence_data["price_date"]
    assert float(data["price"]) == 123.45

def test_fx_rate_query(setup_persistence_data, e2e_api_client: E2EApiClient):
    """Tests that the ingested FX rate can be queried correctly."""
    api_response = e2e_api_client.query(f"/fx-rates?from_currency=USD&to_currency=EUR")
    data = api_response.json()["rates"][0]
    assert data["rate_date"] == setup_persistence_data["price_date"]
    assert float(data["rate"]) == 0.95

def test_transaction_query(setup_persistence_data, e2e_api_client: E2EApiClient):
    """Tests that the ingested transaction can be queried correctly."""
    api_response = e2e_api_client.query(f"/portfolios/{setup_persistence_data['portfolio_id']}/transactions")
    data = api_response.json()["transactions"][0]
    assert data["transaction_id"] == setup_persistence_data["transaction_id"]
    assert float(data["quantity"]) == 100

def test_query_prices_for_unpriced_security_returns_empty_list(setup_persistence_data, e2e_api_client: E2EApiClient):
    """
    Tests that querying the /prices endpoint for a valid security that has
    no price data results in a 200 OK with an empty list.
    """
    security_id_with_no_price = "SEC_NO_PRICE"
    api_response = e2e_api_client.query(f"/prices?security_id={security_id_with_no_price}")
    data = api_response.json()
    assert data["security_id"] == security_id_with_no_price
    assert data["prices"] == []