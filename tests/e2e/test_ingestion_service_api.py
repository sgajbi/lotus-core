# tests/e2e/test_ingestion_service_api.py
import pytest
import requests

from .api_client import E2EApiClient


def test_ingest_empty_transaction_list_succeeds(e2e_api_client: E2EApiClient):
    """
    GIVEN an empty list of transactions
    WHEN posting to the /ingest/transactions endpoint
    THEN the API should return a 202 Accepted response.
    """
    # ARRANGE
    payload = {"transactions": []}

    # ACT
    response = e2e_api_client.ingest("/ingest/transactions", payload)

    # ASSERT
    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == "transaction"
    assert body["accepted_count"] == 0
    assert "job_id" in body
    assert body["message"] == "Transactions accepted for asynchronous ingestion processing."


def test_ingest_malformed_transaction_payload_fails(e2e_api_client: E2EApiClient):
    """
    GIVEN a malformed payload (not a JSON object with a 'transactions' key)
    WHEN posting to the /ingest/transactions endpoint
    THEN the API should return a 422 Unprocessable Entity response.
    """
    # ARRANGE
    # Payload is just a list, not a dictionary with the "transactions" key
    payload = [{"transaction_id": "bad-payload"}]

    # ACT
    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        e2e_api_client.ingest("/ingest/transactions", payload)

    # ASSERT
    assert excinfo.value.response.status_code == 422
