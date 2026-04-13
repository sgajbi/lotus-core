# tests/e2e/test_reliability_pipeline.py
import uuid

import pytest
import requests

from .api_client import E2EApiClient


def test_instrument_ingestion_is_idempotent(e2e_api_client: E2EApiClient, clean_db):
    """
    Tests that ingesting the same instrument twice results in only one record.
    """
    # ARRANGE
    security_id = f"SEC_IDEMPOTENT_{uuid.uuid4()}"
    ingest_payload = {
        "instruments": [
            {
                "securityId": security_id,
                "name": "Idempotent Test Instrument",
                "isin": f"ISIN_{uuid.uuid4()}",
                "instrumentCurrency": "JPY",
                "productType": "Future",
            }
        ]
    }

    # ACT: Ingest the same payload twice
    assert e2e_api_client.ingest("/ingest/instruments", ingest_payload).status_code == 202
    assert e2e_api_client.ingest("/ingest/instruments", ingest_payload).status_code == 202

    # ASSERT: Poll and verify only one record exists
    poll_url = f"/instruments?security_id={security_id}"
    def validation_func(data):
        return data.get("instruments") and len(data["instruments"]) == 1
    query_data = e2e_api_client.poll_for_data(poll_url, validation_func)

    assert query_data["instruments"][0]["name"] == "Idempotent Test Instrument"


def test_portfolio_update_persistence(e2e_api_client: E2EApiClient, clean_db):
    """
    Tests that ingesting a portfolio with an existing ID updates the record.
    """
    # ARRANGE
    portfolio_id = f"E2E_UPDATE_PORT_{uuid.uuid4()}"
    initial_payload = {
        "portfolios": [
            {
                "portfolioId": portfolio_id,
                "baseCurrency": "AUD",
                "status": "PENDING",
                "openDate": "2024-01-01",
                "cifId": "CIF_U_1",
                "riskExposure": "a",
                "investmentTimeHorizon": "b",
                "portfolioType": "c",
                "bookingCenter": "d",
            }
        ]
    }
    update_payload = {
        "portfolios": [
            {
                "portfolioId": portfolio_id,
                "baseCurrency": "AUD",
                "status": "ACTIVE",
                "openDate": "2024-01-01",
                "cifId": "CIF_U_1",
                "riskExposure": "a",
                "investmentTimeHorizon": "b",
                "portfolioType": "c",
                "bookingCenter": "d",
            }
        ]
    }

    e2e_api_client.ingest("/ingest/portfolios", initial_payload)
    poll_url = f"/portfolios?portfolio_id={portfolio_id}"
    e2e_api_client.poll_for_data(
        poll_url,
        lambda data: data.get("portfolios") and data["portfolios"][0]["status"] == "PENDING",
    )

    # ACT
    assert e2e_api_client.ingest("/ingest/portfolios", update_payload).status_code == 202

    # ASSERT
    e2e_api_client.poll_for_data(
        poll_url,
        lambda data: data.get("portfolios") and data["portfolios"][0]["status"] == "ACTIVE",
    )


def test_transaction_persists_after_portfolio_arrives(e2e_api_client: E2EApiClient, clean_db):
    """
    Tests that a transaction consumer retries and succeeds if the portfolio arrives late.
    """
    # ARRANGE
    portfolio_id = f"E2E_RETRY_PORT_{uuid.uuid4()}"
    transaction_id = f"TXN_RETRY_{uuid.uuid4()}"
    transaction_payload = {
        "transactions": [
            {
                "transaction_id": transaction_id,
                "portfolio_id": portfolio_id,
                "instrument_id": "RETRY",
                "security_id": "SEC_RETRY",
                "transaction_date": "2025-08-01T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 10,
                "price": 1,
                "gross_transaction_amount": 10,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    portfolio_payload = {
        "portfolios": [
            {
                "portfolioId": portfolio_id,
                "baseCurrency": "USD",
                "openDate": "2024-01-01",
                "cifId": "CIF_R_1",
                "status": "ACTIVE",
                "riskExposure": "a",
                "investmentTimeHorizon": "b",
                "portfolioType": "c",
                "bookingCenter": "d",
            }
        ]
    }

    # ACT: Ingest the transaction first and prove it is not queryable before the
    # dependent portfolio arrives.
    assert e2e_api_client.ingest("/ingest/transactions", transaction_payload).status_code == 202
    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        e2e_api_client.query(f"/portfolios/{portfolio_id}/transactions")
    assert excinfo.value.response.status_code == 404

    assert e2e_api_client.ingest("/ingest/portfolios", portfolio_payload).status_code == 202

    # ASSERT: Poll for the transaction, which should now have been persisted.
    poll_url = f"/portfolios/{portfolio_id}/transactions"
    def validation_func(data):
        return data.get("transactions") and len(data["transactions"]) == 1
    query_data = e2e_api_client.poll_for_data(poll_url, validation_func)

    assert query_data["transactions"][0]["transaction_id"] == transaction_id
