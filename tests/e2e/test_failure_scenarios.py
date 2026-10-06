# tests/e2e/test_failure_scenarios.py
import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests
from confluent_kafka import Consumer
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
)
from sqlalchemy import exc, text
from sqlalchemy.orm import Session

from scripts.quality.ci_service_sets import (
    E2E_RECOVERY_HEALTH_PORT_ENV,
    E2E_RECOVERY_SERVICES,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.processing_state_repository import (  # noqa: E501
    cost_basis_processing_lock_key,
)
from tests.test_support.docker_stack import resolve_compose_file
from tests.test_support.native_consumer_boundary import (
    assert_financial_oracle,
    assert_worker_advisory_admission,
    committed_offset,
    financial_snapshot,
    publish,
    wait_for_value,
)
from tests.test_support.output_control import emit_test_output
from tests.test_support.runtime.compose_fault_recovery import (
    ComposeFaultRecoveryBoundary,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    portfolio_record,
)

from .api_client import E2EApiClient


def _core_service_health_urls() -> list[str]:
    return [
        f"http://localhost:{os.environ[E2E_RECOVERY_HEALTH_PORT_ENV[service]]}/health/ready"
        for service in E2E_RECOVERY_SERVICES
    ]


def _native_compose(*args):
    return subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            resolve_compose_file(str(Path(__file__).resolve().parents[2])),
            "-p",
            os.environ["COMPOSE_PROJECT_NAME"],
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout


def _native_worker_logs():
    return _native_compose(
        "logs", "--no-color", "--timestamps", "portfolio_transaction_processing_service"
    )


def _native_worker_identity():
    root = Path(__file__).resolve().parents[2]
    directory = root / "output/runtime-image-set"
    verified = (directory / "verified-source-sha").read_text().strip()
    manifest = json.loads((directory / "manifest.json").read_text())
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    assert verified == manifest["source_commit_sha"] == head
    service = "portfolio_transaction_processing_service"
    container = _native_compose("ps", "--quiet", service).strip()
    inspection = json.loads(
        subprocess.run(
            ["docker", "inspect", container],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    )[0]
    record = next(row for row in manifest["services"] if row["service"] == service)
    assert inspection["Image"] == record["image_id"]
    image = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", inspection["Image"]],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    )[0]
    assert image["Config"]["Labels"]["org.opencontainers.image.revision"] == head
    assert (
        inspection["Config"]["Labels"]["com.docker.compose.project"]
        == os.environ["COMPOSE_PROJECT_NAME"]
    )
    return {
        "source": head,
        "image_id": inspection["Image"],
        "container": container,
        "command": inspection["Config"]["Cmd"],
        "project": inspection["Config"]["Labels"]["com.docker.compose.project"],
        "ips": [
            address
            for network in inspection["NetworkSettings"]["Networks"].values()
            for address in (network["IPAddress"], network.get("GlobalIPv6Address"))
            if address
        ],
        "manifest_hash": manifest["content_hash"],
    }


def _deployed_native_boundary(db_engine, *, forced):
    service = "portfolio_transaction_processing_service"
    health_url = (
        f"http://localhost:{os.environ['LOTUS_TRANSACTION_PROCESSING_HOST_PORT']}/health/ready"
    )
    recovery = ComposeFaultRecoveryBoundary(
        project_name=os.environ["COMPOSE_PROJECT_NAME"],
        faulted_service=service,
        recovery_services=(),
        faulted_service_ready=lambda: wait_for_service_ready(health_url),
        recovery_services_ready=lambda: None,
        compose_file=resolve_compose_file(str(Path(__file__).resolve().parents[2])),
    )
    primary_error = None
    try:
        _exercise_deployed_native_boundary(db_engine, recovery, forced=forced)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            recovery.restore()
        except BaseException as restoration_error:
            if primary_error is None:
                raise
            primary_error.add_note(f"Worker restoration also failed: {restoration_error!r}")


def _exercise_deployed_native_boundary(db_engine, recovery, *, forced):
    """Use real admission/SQL/offset/lifecycle observations, not exit alone."""
    service = "portfolio_transaction_processing_service"
    group = "portfolio_transaction_processing_group"
    topic = KAFKA_TRANSACTIONS_PERSISTED_TOPIC
    identity = _native_worker_identity()
    suffix = uuid.uuid4().hex[:12]
    portfolio, security = f"DEP-NB-{suffix}", f"DEP-EQ-{suffix}"
    event = booked_transaction_event(
        transaction_id=f"DEP-BUY-{suffix}",
        portfolio_id=portfolio,
        security_id=security,
        transaction_date=datetime(2026, 1, 10, 10, tzinfo=UTC),
        transaction_type="BUY",
        quantity="10",
        price="25.50",
        gross_amount="255",
        trade_currency="SGD",
    )
    with Session(db_engine) as session:
        session.add_all(
            [
                portfolio_record(portfolio, base_currency="SGD"),
                instrument_record(
                    security,
                    name="Deployed native equity",
                    isin=f"DEP_ISIN_{suffix}",
                    currency="SGD",
                ),
                canonical_transaction_record(event),
            ]
        )
        session.commit()
    prior_logs = _native_worker_logs()
    lock = cost_basis_processing_lock_key(portfolio, security)
    baseline = committed_offset(group, topic)
    with db_engine.connect() as holder:
        holder.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock})
        holder_pid = holder.scalar(text("SELECT pg_backend_pid()"))
        try:
            first = publish(topic, event.model_dump(mode="json"), portfolio)
            later = publish(topic, event.model_dump(mode="json"), portfolio)
            assert later == first + 1

            def admission():
                with db_engine.connect() as observer:
                    return (
                        observer.execute(
                            text(
                                "SELECT a.pid, a.client_addr::text AS client_addr_raw, "
                                "host(a.client_addr) AS client_host, a.query, "
                                "pg_blocking_pids(a.pid) AS blocking_pids, "
                                "a.wait_event_type, a.wait_event FROM pg_stat_activity a "
                                "WHERE :holder = ANY(pg_blocking_pids(a.pid)) "
                                "AND a.wait_event_type = 'Lock' AND a.wait_event = 'advisory'"
                            ),
                            {"holder": holder_pid},
                        )
                        .mappings()
                        .all()
                    )

            try:
                admitted = wait_for_value(admission, bool)
            except TimeoutError as error:
                error.add_note(
                    json.dumps(
                        {"worker": identity, "holder_pid": holder_pid, "production_lock_key": lock},
                        sort_keys=True,
                    )
                )
                raise
            # Only production workers run in this live-worker invocation. The
            # exact production lock key and real backend wait establish admission.
            assert_worker_advisory_admission(
                admitted, identity, holder_pid=holder_pid, lock_key=lock
            )
            ids = (f"{topic}-0-{first}",)
            before = financial_snapshot(db_engine, portfolio, security, event_ids=ids)
            assert all(
                not before[name]
                for name in ("lots", "cash", "positions", "receipts", "outbox", "checkpoint")
            )
            assert before["cost"] == [(event.transaction_id, None, None)]
            assert committed_offset(group, topic) == baseline
            _native_compose("kill", "--signal", "SIGKILL" if forced else "SIGTERM", service)
            if not forced:

                def shutdown_started():
                    delta = _native_worker_logs()[len(prior_logs) :]
                    return any(
                        "kafka.consumer.shutdown_started" in line and group in line
                        for line in delta.splitlines()
                    )

                wait_for_value(shutdown_started, bool)
            else:
                container = _native_compose("ps", "--all", "--quiet", service).strip()
                state = subprocess.run(
                    ["docker", "inspect", "--format", "{{.State.Running}}", container],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                ).stdout.strip()
                assert state == "false"
                assert committed_offset(group, topic) == baseline
                assert financial_snapshot(db_engine, portfolio, security, event_ids=ids) == before
        finally:
            holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock})
            holder.commit()
            if forced:
                recovery.restore()

    try:
        expected_ack = later + 1 if forced else first + 1
        wait_for_value(lambda: committed_offset(group, topic), lambda value: value == expected_ack)
        snapshot = financial_snapshot(db_engine, portfolio, security, event_ids=ids)
        assert_financial_oracle(snapshot, event.transaction_id)
        assert snapshot["receipts"][0][0] == f"{topic}-0-{first}"
        if not forced:

            def closed():
                delta = _native_worker_logs()[len(prior_logs) :]
                return [
                    line
                    for line in delta.splitlines()
                    if "kafka.consumer.shutdown_completed" in line and group in line
                ]

            completed = wait_for_value(closed, bool)
            assert all("succeeded" in line for line in completed)
            assert committed_offset(group, topic) == first + 1
            recovery.restore()
            wait_for_value(lambda: committed_offset(group, topic), lambda value: value == later + 1)
            assert financial_snapshot(db_engine, portfolio, security, event_ids=ids) == snapshot
        emit_test_output(
            json.dumps(
                {
                    "native_boundary": "forced-redelivery" if forced else "graceful-drain",
                    "group": group,
                    "topic": topic,
                    "partition": 0,
                    "first_offset": first,
                    "later_offset": later,
                    "final_offset": later + 1,
                    "lock_key": lock,
                    "admitted_backends": [dict(row) for row in admitted],
                    "financial": snapshot,
                    "identity": identity,
                },
                default=str,
            )
        )
    finally:
        recovery.restore()


def test_deployed_graceful_stop_drains_admitted_financial_work(
    docker_services,
    db_engine,
    clean_db_module,
):
    _deployed_native_boundary(db_engine, forced=False)


def test_deployed_forced_interruption_redelivers_without_duplicate_financial_effects(
    docker_services,
    db_engine,
    clean_db_module,
):
    _deployed_native_boundary(db_engine, forced=True)


def _wait_for_core_services_ready() -> None:
    for health_url in _core_service_health_urls():
        wait_for_service_ready(health_url, timeout=120)


def _poll_until(
    predicate: Callable[[], bool],
    *,
    timeout: int,
    interval: float,
    failure_message: str,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    pytest.fail(failure_message)


def wait_for_postgres_ready(db_engine, timeout=30):
    """Waits for the PostgreSQL container to be ready for connections."""

    def _is_ready() -> bool:
        try:
            with db_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except (exc.OperationalError, exc.DBAPIError):
            return False

    _poll_until(
        _is_ready,
        timeout=timeout,
        interval=1,
        failure_message=f"PostgreSQL did not become ready within {timeout} seconds.",
    )
    emit_test_output("\n--- PostgreSQL is ready ---", verbose_only=True)


def wait_for_postgres_unavailable(db_engine, timeout=30):
    """Waits for PostgreSQL to stop accepting connections after an outage starts."""

    def _is_unavailable() -> bool:
        try:
            with db_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except (exc.OperationalError, exc.DBAPIError):
            return True
        return False

    _poll_until(
        _is_unavailable,
        timeout=timeout,
        interval=0.5,
        failure_message=f"PostgreSQL did not become unavailable within {timeout} seconds.",
    )
    emit_test_output("\n--- PostgreSQL outage confirmed ---", verbose_only=True)


def wait_for_service_ready(service_url: str, timeout: int = 60):
    """Polls a service's /health/ready endpoint until it returns 200 OK."""

    def _is_ready() -> bool:
        try:
            response = requests.get(service_url, timeout=2)
            return bool(response.status_code == 200)
        except requests.ConnectionError:
            return False

    _poll_until(
        _is_ready,
        timeout=timeout,
        interval=2,
        failure_message=(
            f"Service at {service_url} did not become healthy within {timeout} seconds."
        ),
    )
    emit_test_output(f"\n--- Service at {service_url} is healthy ---", verbose_only=True)


def test_db_outage_recovery(
    docker_services, db_engine, clean_db_module, e2e_api_client: E2EApiClient, poll_db_until
):
    """
    Tests that the persistence-service can recover from a transient DB outage,
    successfully process a message after retrying, and does not send the
    message to the DLQ.
    """
    # 1. ARRANGE: Define test data
    suffix = uuid.uuid4().hex[:8].upper()
    portfolio_id = f"E2E_FAIL_PORT_{suffix}"
    security_id = f"SEC_FAIL_{suffix}"
    instrument_id = f"FAIL_INST_{suffix}"
    transaction_id_before = f"{portfolio_id}_TXN_BEFORE"
    transaction_id_after = f"{portfolio_id}_TXN_AFTER"

    # 2. ARRANGE: Set up a Kafka consumer for the DLQ topic
    dlq_consumer_conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": f"test-dlq-checker-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
    }
    dlq_consumer = Consumer(dlq_consumer_conf)
    dlq_consumer.subscribe([KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC])

    # 3. ARRANGE: Ingest and settle the reference data this database-recovery
    # scenario is not intended to exercise. Leaving the instrument unresolved
    # creates a permanent downstream dependency failure that contaminates later
    # E2E modules and obscures the PostgreSQL recovery contract under test.
    portfolio_payload = {
        "portfolios": [
            {
                "portfolio_id": portfolio_id,
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "client_id": f"FAIL_CIF_{suffix}",
                "status": "ACTIVE",
                "risk_exposure": "a",
                "investment_time_horizon": "b",
                "portfolio_type": "c",
                "booking_center_code": "d",
            }
        ]
    }
    e2e_api_client.ingest("/ingest/portfolios", portfolio_payload)
    e2e_api_client.ingest(
        "/ingest/instruments",
        {
            "instruments": [
                {
                    "security_id": security_id,
                    "name": "Database Recovery Test Instrument",
                    "isin": f"FAIL_ISIN_{suffix}",
                    "currency": "USD",
                    "product_type": "Equity",
                }
            ]
        },
    )
    e2e_api_client.poll_for_data(
        f"/portfolios?portfolio_id={portfolio_id}",
        lambda data: data.get("portfolios") and len(data["portfolios"]) == 1,
    )
    e2e_api_client.poll_for_data(
        f"/instruments?security_id={security_id}",
        lambda data: data.get("instruments") and len(data["instruments"]) == 1,
    )

    # 4. ARRANGE: Persist one transaction before outage.
    transaction_payload_before = {
        "transactions": [
            {
                "transaction_id": transaction_id_before,
                "portfolio_id": portfolio_id,
                "instrument_id": instrument_id,
                "security_id": security_id,
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
    emit_test_output("\n--- Stopping PostgreSQL container ---")
    with ComposeFaultRecoveryBoundary(
        project_name=os.environ["COMPOSE_PROJECT_NAME"],
        faulted_service="postgres",
        recovery_services=E2E_RECOVERY_SERVICES,
        faulted_service_ready=lambda: wait_for_postgres_ready(db_engine, timeout=60),
        recovery_services_ready=_wait_for_core_services_ready,
    ) as outage:
        wait_for_postgres_unavailable(db_engine)
        emit_test_output("\n--- Reconciling PostgreSQL and dependent services ---")
        outage.restore()
    emit_test_output("\n--- Core services fully recovered after outage ---")

    # 7. ACT/ASSERT: Ingest and persist a new transaction after recovery.
    transaction_payload_after = {
        "transactions": [
            {
                "transaction_id": transaction_id_after,
                "portfolio_id": portfolio_id,
                "instrument_id": instrument_id,
                "security_id": security_id,
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
    emit_test_output(
        f"\n--- Transaction '{transaction_id_after}' successfully persisted after recovery ---",
        verbose_only=True,
    )

    # 8. ASSERT: Verify the DLQ is empty
    emit_test_output("\n--- Verifying DLQ is empty ---", verbose_only=True)
    msg = dlq_consumer.poll(timeout=10)
    dlq_consumer.close()

    assert msg is None, (
        f"A message was unexpectedly found in the DLQ: {msg.value() if msg else 'None'}"
    )
    emit_test_output("\n--- DLQ verified to be empty ---", verbose_only=True)
