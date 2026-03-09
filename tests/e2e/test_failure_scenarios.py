# tests/e2e/test_failure_scenarios.py
import os
import subprocess
import time
import uuid

import pytest
import requests
from confluent_kafka import Consumer
from portfolio_common.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_PERSISTENCE_DLQ_TOPIC
from sqlalchemy import exc, text

from .api_client import E2EApiClient


def _compose_args(*compose_args: str) -> list[str]:
    project_name = os.environ["COMPOSE_PROJECT_NAME"]
    return ["docker", "compose", "-p", project_name, *compose_args]


def _core_service_health_urls() -> list[str]:
    return [
        f"http://localhost:{os.environ['LOTUS_PERSISTENCE_HOST_PORT']}/health/ready",
        f"http://localhost:{os.environ['LOTUS_POSITION_CALCULATOR_HOST_PORT']}/health/ready",
        f"http://localhost:{os.environ['LOTUS_CASHFLOW_CALCULATOR_HOST_PORT']}/health/ready",
        f"http://localhost:{os.environ['LOTUS_COST_CALCULATOR_HOST_PORT']}/health/ready",
        f"http://localhost:{os.environ['LOTUS_POSITION_VALUATION_HOST_PORT']}/health/ready",
        f"http://localhost:{os.environ['LOTUS_TIMESERIES_GENERATOR_HOST_PORT']}/health/ready",
        f"http://localhost:{os.environ['LOTUS_INGESTION_HOST_PORT']}/health/ready",
        f"http://localhost:{os.environ['LOTUS_QUERY_HOST_PORT']}/health/ready",
    ]


def wait_for_postgres_ready(db_engine, timeout=30):
    """Waits for the PostgreSQL container to be ready for connections."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with db_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("\n--- PostgreSQL is ready ---")
            return
        except (exc.OperationalError, exc.DBAPIError):
            time.sleep(1)
    pytest.fail(f"PostgreSQL did not become ready within {timeout} seconds.")


def wait_for_service_ready(service_url: str, timeout: int = 60):
    """Polls a service's /health/ready endpoint until it returns 200 OK."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(service_url, timeout=2)
            if response.status_code == 200:
                print(f"\n--- Service at {service_url} is healthy ---")
                return
        except requests.ConnectionError:
            pass  # Service is not up yet, ignore and retry
        time.sleep(2)
    pytest.fail(f"Service at {service_url} did not become healthy within {timeout} seconds.")


def test_db_outage_recovery(
    docker_services, db_engine, clean_db_module, e2e_api_client: E2EApiClient, poll_db_until
):
    """
    Tests that the persistence-service can recover from a transient DB outage,
    successfully process a message after retrying, and does not send the
    message to the DLQ.
    """
    # 1. ARRANGE: Define test data
    portfolio_id = f"E2E_FAIL_PORT_{uuid.uuid4()}"
    transaction_id_before = f"E2E_FAIL_TXN_BEFORE_{uuid.uuid4()}"
    transaction_id_after = f"E2E_FAIL_TXN_AFTER_{uuid.uuid4()}"

    # 2. ARRANGE: Set up a Kafka consumer for the DLQ topic
    dlq_consumer_conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": f"test-dlq-checker-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
    }
    dlq_consumer = Consumer(dlq_consumer_conf)
    dlq_consumer.subscribe([KAFKA_PERSISTENCE_DLQ_TOPIC])

    # 3. ARRANGE: Ingest prerequisite portfolio data
    portfolio_payload = {
        "portfolios": [
            {
                "portfolio_id": portfolio_id,
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "client_id": "FAIL_CIF",
                "status": "ACTIVE",
                "risk_exposure": "a",
                "investment_time_horizon": "b",
                "portfolio_type": "c",
                "booking_center_code": "d",
            }
        ]
    }
    e2e_api_client.ingest("/ingest/portfolios", portfolio_payload)

    # 4. ARRANGE: Persist one transaction before outage.
    transaction_payload_before = {
        "transactions": [
            {
                "transaction_id": transaction_id_before,
                "portfolio_id": portfolio_id,
                "instrument_id": "FAIL_INST",
                "security_id": "SEC_FAIL",
                "transaction_date": "2025-08-05T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    e2e_api_client.ingest("/ingest/transactions", transaction_payload_before)
    poll_db_until(
        query="SELECT 1 FROM transactions WHERE transaction_id = :txn_id",
        params={"txn_id": transaction_id_before},
        validation_func=lambda r: r is not None,
        timeout=60,
        fail_message=f"Pre-outage transaction '{transaction_id_before}' was not persisted.",
    )

    # 5. ACT: Simulate database outage.
    print("\n--- Stopping PostgreSQL container ---")
    subprocess.run(_compose_args("stop", "postgres"), check=True, capture_output=True)

    # Give a moment for persistence-service to observe the outage.
    time.sleep(5)

    print("\n--- Starting PostgreSQL container ---")
    subprocess.run(_compose_args("start", "postgres"), check=True, capture_output=True)
    wait_for_postgres_ready(db_engine)

    print("\n--- Restarting persistence_service to ensure DB reconnection ---")
    subprocess.run(
        _compose_args("restart", "persistence_service"), check=True, capture_output=True
    )

    # 6. ACT: Wait for the persistence service to become healthy again
    wait_for_service_ready(f"http://localhost:{os.environ['LOTUS_PERSISTENCE_HOST_PORT']}/health/ready")

    # 7. ACT/ASSERT: Ingest and persist a new transaction after recovery.
    transaction_payload_after = {
        "transactions": [
            {
                "transaction_id": transaction_id_after,
                "portfolio_id": portfolio_id,
                "instrument_id": "FAIL_INST",
                "security_id": "SEC_FAIL",
                "transaction_date": "2025-08-05T10:05:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    e2e_api_client.ingest("/ingest/transactions", transaction_payload_after)
    poll_db_until(
        query="SELECT 1 FROM transactions WHERE transaction_id = :txn_id",
        params={"txn_id": transaction_id_after},
        validation_func=lambda r: r is not None,
        timeout=60,  # The service should recover and process well within this time.
        fail_message=f"Transaction '{transaction_id_after}' was not persisted after DB recovery.",
    )
    print(f"\n--- Transaction '{transaction_id_after}' successfully persisted after recovery ---")

    # 8. ASSERT: Verify the DLQ is empty
    print("\n--- Verifying DLQ is empty ---")
    msg = dlq_consumer.poll(timeout=10)
    dlq_consumer.close()

    assert (
        msg is None
    ), f"A message was unexpectedly found in the DLQ: {msg.value() if msg else 'None'}"
    print("\n--- DLQ verified to be empty ---")

    # 9. RECOVERY BARRIER: restart all core services and wait for end-to-end readiness
    print("\n--- Restarting all core services after DB outage scenario ---")
    subprocess.run(
        _compose_args(
            "restart",
            "ingestion_service",
            "query_service",
            "persistence_service",
            "position_calculator_service",
            "cashflow_calculator_service",
            "cost_calculator_service",
            "position_valuation_calculator",
            "timeseries_generator_service",
        ),
        check=True,
        capture_output=True,
    )
    for health_url in _core_service_health_urls():
        wait_for_service_ready(health_url, timeout=120)
    print("\n--- Core services fully recovered after outage test ---")
