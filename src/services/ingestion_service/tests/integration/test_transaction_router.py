# services/ingestion_service/tests/integration/test_transaction_router.py
import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock, call
from datetime import datetime

from portfolio_common.config import KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio


async def test_ingest_transactions_success(
    test_client: AsyncClient, mock_kafka_producer: MagicMock
):
    """
    GIVEN a valid list of transactions
    WHEN the /ingest/transactions endpoint is called
    THEN it should return a 202 Accepted status
    AND call the kafka producer's publish_message method for each transaction
    """
    # GIVEN
    transaction_payload = {
        "transactions": [
            {
                "transaction_id": "INT_TEST_001",
                "portfolio_id": "PORT_INT_01",
                "instrument_id": "AAPL",
                "security_id": "SEC_AAPL",
                "transaction_date": "2025-07-31T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 10.0,
                "price": 150.0,
                "gross_transaction_amount": 1500.0,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": "INT_TEST_002",
                "portfolio_id": "PORT_INT_01",
                "instrument_id": "GOOG",
                "security_id": "SEC_GOOG",
                "transaction_date": "2025-07-31T11:00:00Z",
                "transaction_type": "BUY",
                "quantity": 5.0,
                "price": 1000.0,
                "gross_transaction_amount": 5000.0,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }

    # WHEN
    response = await test_client.post("/ingest/transactions", json=transaction_payload)

    # THEN
    assert response.status_code == 202
    assert response.json() == {
        "message": "Successfully queued 2 transactions for processing."
    }

    # Verify that the kafka producer was called correctly for each transaction
    assert mock_kafka_producer.publish_message.call_count == 2
    
    # Check the content of the first published message
    first_call = mock_kafka_producer.publish_message.call_args_list[0]
    assert first_call.kwargs["topic"] == KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC
    assert first_call.kwargs["key"] == "INT_TEST_001"
    assert first_call.kwargs["value"]["portfolio_id"] == "PORT_INT_01"

    # Check the content of the second published message
    second_call = mock_kafka_producer.publish_message.call_args_list[1]
    assert second_call.kwargs["topic"] == KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC
    assert second_call.kwargs["key"] == "INT_TEST_002"
    assert second_call.kwargs["value"]["instrument_id"] == "GOOG"