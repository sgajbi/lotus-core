"""Prove bounded lock observations without financial writes or application workers."""

from __future__ import annotations

import copy
import json
import sys
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from psycopg2.extras import RealDictCursor
from sqlalchemy.engine import Engine

from scripts.operations.performance.load_completion_diagnostics import (
    _diagnostic_database_engine,
    _load_consumer_metrics,
    _load_database_probes,
    _qualify_lock_edges,
)


def _close_owned_probes(
    connections: dict[str, Any],
    observer_engine: Engine | None,
    worker: threading.Thread | None,
    primary: BaseException | None,
) -> None:
    errors: list[Exception] = []

    def attempt(label: str, action: Callable[[], Any]) -> None:
        try:
            action()
        except Exception as exc:
            exc.add_note(label)
            errors.append(exc)

    if head := connections.get("head"):
        attempt("release owned holder", head.rollback)
        attempt("close owned holder socket", head.driver_connection.close)
    if waiter := connections.get("waiter"):
        if worker is not None and worker.is_alive():
            attempt("cancel owned waiter", waiter.driver_connection.cancel)
        # Close the owned socket before bounded join, including holder-release failure.
        attempt("close owned waiter socket", waiter.driver_connection.close)
    if worker is not None:
        attempt("bounded owned waiter join", lambda: worker.join(timeout=2))
        if worker.is_alive():
            errors.append(RuntimeError("Owned waiter thread did not stop after cancel/close"))
    for name, connection in reversed(list(connections.items())):
        if name not in {"head", "waiter"}:
            attempt("rollback owned " + name, connection.rollback)
        attempt("close owned " + name, connection.close)
    if observer_engine is not None:
        attempt("dispose owned observer engine", observer_engine.dispose)
    if errors:
        if primary is not None:
            for exc in errors:
                primary.add_note("Cleanup failure: " + repr(exc))
        else:
            raise ExceptionGroup("Owned diagnostic cleanup failures", errors)


@pytest.mark.parametrize("has_primary", [False, True])
def test_probe_cleanup_attempts_every_resource_and_preserves_primary(has_primary: bool) -> None:
    head, waiter, noise, observer, engine, worker = [MagicMock() for _ in range(6)]
    head.rollback.side_effect = RuntimeError("holder release failed")
    worker.join.side_effect = RuntimeError("join failed")
    worker.is_alive.return_value = True
    noise.close.side_effect = RuntimeError("close failed")
    primary = ValueError("original probe failed") if has_primary else None
    if primary is None:
        with pytest.raises(ExceptionGroup) as failure:
            _close_owned_probes(
                {"noise": noise, "head": head, "waiter": waiter, "observer": observer},
                engine,
                worker,
                None,
            )
        assert len(failure.value.exceptions) == 4
    else:
        _close_owned_probes(
            {"noise": noise, "head": head, "waiter": waiter, "observer": observer},
            engine,
            worker,
            primary,
        )
        assert str(primary) == "original probe failed" and len(primary.__notes__) == 4
    waiter.driver_connection.cancel.assert_called_once()
    head.rollback.assert_called_once()
    head.driver_connection.close.assert_called_once()
    waiter.driver_connection.close.assert_called_once()
    worker.join.assert_called_once_with(timeout=2)
    for connection in (observer, waiter, head, noise):
        connection.close.assert_called_once()
    engine.dispose.assert_called_once()


def test_probe_partial_allocation_cleanup_closes_first_connection() -> None:
    noise = MagicMock()
    _close_owned_probes({"noise": noise}, None, None, ValueError("next allocation failed"))
    noise.rollback.assert_called_once()
    noise.close.assert_called_once()


def test_native_lock_probe_prioritizes_birth_qualified_blocker_and_waiter(
    db_engine: Engine,
) -> None:
    key = uuid.uuid4().int % (2**30)
    scope = {
        "portfolio_id": "CORE730_DIAGNOSTIC_NO_FINANCIAL_ROWS",
        "submitted_ids": [],
        "ingestion_job_ids": [],
    }
    connections: dict[str, Any] = {}
    observer_engine: Engine | None = None
    worker: threading.Thread | None = None
    started, finished = threading.Event(), threading.Event()
    worker_errors: list[Exception] = []
    try:
        # Start cleanup coverage before the first allocation, including partial failure.
        for name in ("noise", "head", "waiter"):
            connections[name] = db_engine.raw_connection()
        noise, head, waiter = [connections[name] for name in ("noise", "head", "waiter")]
        observer_engine = _diagnostic_database_engine(
            db_engine.url.render_as_string(hide_password=False)
        )
        connections["observer"] = observer = observer_engine.raw_connection()
        identities = []
        for connection, name in (
            (noise, "persistence-service"),
            (head, "lotus-core-test"),
            (waiter, "portfolio-transaction-processing"),
        ):
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config(%s,%s,false)", ("application_name", name))
                cursor.execute(
                    "SELECT pid,backend_start FROM pg_stat_activity WHERE pid=pg_backend_pid()"
                )
                identities.append(cursor.fetchone())
        noise_pid, head_pid, waiter_pid = [identity[0] for identity in identities]
        assert noise_pid < head_pid < waiter_pid
        with noise.cursor() as cursor:
            for offset in range(30):
                cursor.execute("SELECT pg_advisory_xact_lock(%s,%s)", (key, offset))
        with head.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s,%s)", (key, 100))

        def block() -> None:
            try:
                with waiter.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '10s'")
                    started.set()
                    cursor.execute("SELECT pg_advisory_xact_lock(%s,%s)", (key, 100))
            except Exception as exc:
                worker_errors.append(exc)
            finally:
                finished.set()

        worker = threading.Thread(target=block, daemon=True)
        worker.start()
        assert started.wait(timeout=2)
        observer.set_session(readonly=True, autocommit=True)
        deadline = time.monotonic() + 5
        with observer.cursor() as cursor:
            cursor.execute("SET lock_timeout = '100ms'")
            while True:
                assert not finished.is_set(), repr(worker_errors)
                cursor.execute("SELECT pg_blocking_pids(%s)", (waiter_pid,))
                if cursor.fetchone()[0] == [head_pid]:
                    break
                assert time.monotonic() < deadline, "Native waiter/blocker barrier not observed"
                # Bounded condition polling: elapsed time never establishes a wait.
                finished.wait(timeout=0.01)
        result = _load_database_probes(observer, scope, RealDictCursor)
        waits = result["runtime_db_waits"]
        sample = waits["original_sample"]
        assert sample["original_rows"] == len(waits["rows"])
        assert sample["detail_status"] == "retained"
        for index, (native_row, projected) in enumerate(
            zip(waits["rows"], sample["rows"], strict=True)
        ):
            birth = native_row["backend_start"]
            assert isinstance(birth, datetime) and birth.utcoffset() is not None
            assert projected == {
                "sample_index": index,
                "backend": {
                    "status": "observed",
                    "value": {
                        "pid": native_row["pid"],
                        "database_oid": native_row["database_oid"],
                        "backend_start": birth.astimezone(UTC).isoformat(),
                    },
                },
            }
        assert {row["backend"]["value"]["pid"] for row in sample["rows"]} >= {head_pid, waiter_pid}
        json.dumps(sample, allow_nan=False)
        locks = result["runtime_db_locks"]
        assert locks["status"] == "observed"
        assert locks["truncated"] and locks["observed_total_rows"] > 20
        assert len(locks["rows"]) == 20
        qualified = [row for row in locks["rows"] if row.get("edge_identity_status") == "observed"]
        assert {row["blocking_role"] for row in qualified} == {"blocker_head", "waiting_edge"}
        for row in qualified:
            assert row["waiter_pid"] == waiter_pid and row["blocker_pid"] == head_pid
            assert row["waiter_backend_start"] == identities[2][1]
            assert row["blocker_backend_start"] == identities[1][1]
            assert row["locktype"] == "advisory" and row["relation_oid"] is None
            assert row["exact_await"] == "MISSING"
        # Native returned rows with a deliberately stale previous observation.
        # This proves admission refusal, not actual PostgreSQL PID reuse.
        stale_rows = copy.deepcopy(qualified)
        stale_waits = copy.deepcopy(result["runtime_db_waits"]["rows"])
        for row in stale_waits:
            if row["pid"] == head_pid:
                row["backend_start"] -= timedelta(seconds=1)
        _qualify_lock_edges(stale_rows, stale_waits)
        assert all(row["edge_identity_status"] == "stale_birth" for row in stale_rows)
        assert all(row["blocking_role"] == "unqualified" for row in stale_rows)
        print(
            "CORE730_LOCK_PROOF "
            + json.dumps(
                {
                    "native_wait_barrier": {"waiter": waiter_pid, "blockers": [head_pid]},
                    "unrelated_advisory_locks": 30,
                    "noise_pid": noise_pid,
                    "qualified_rows": qualified,
                    "original_wait_sample": sample,
                    "observed_total_rows": locks["observed_total_rows"],
                    "truncated": locks["truncated"],
                    "stale_observation_refused": True,
                },
                default=str,
                allow_nan=False,
            )
        )
    finally:
        _close_owned_probes(connections, observer_engine, worker, sys.exception())


def _serve_consumer_metrics(monkeypatch: pytest.MonkeyPatch, exposition: str) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [exposition.encode()]
    monkeypatch.setattr(
        "scripts.operations.performance.load_completion_diagnostics.requests.get",
        MagicMock(return_value=response),
    )


@pytest.mark.parametrize(
    ("name", "extra_labels"),
    [
        ("kafka_consumer_in_flight_messages", ""),
        ("kafka_consumer_backlog_pressure_total", ',reason="ordering_key_busy"'),
        ("kafka_consumer_partition_lag_messages", ',partition="0"'),
    ],
)
@pytest.mark.parametrize(
    ("service", "topic", "group"),
    [
        ("TXNPROC", "transactions.persisted", "portfolio_transaction_processing_group"),
        (
            "TXNREPLAY",
            "transactions.reprocessing.requested",
            "portfolio_transaction_replay_request_group",
        ),
    ],
)
def test_consumer_metrics_supported_selected_sample(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    extra_labels: str,
    service: str,
    topic: str,
    group: str,
) -> None:
    labels = f'service="{service}",topic="{topic}",group_id="{group}"'
    _serve_consumer_metrics(monkeypatch, f"{name}{{{labels}{extra_labels}}} 3\n")

    result = _load_consumer_metrics("http://metrics.test/metrics")

    assert result["status"] == "observed"
    assert result["reason"] is None
    assert result["recognized_samples"] == 1
    assert result["filtered_samples"] == 0
    assert [(sample["name"], sample["value"]) for sample in result["samples"]] == [(name, 3)]


def test_consumer_metrics_filter_cohosted_consumers_before_selected_privacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_consumer_metrics(
        monkeypatch,
        'kafka_consumer_in_flight_messages{service="BOOKCOST",topic="bookcost.reprocessing",'
        'group_id="bookcost_group"} 9\n'
        'kafka_consumer_in_flight_messages{service="CAMANIFEST",topic="corporate.actions",'
        'group_id="manifest_group",tenant_id="private"} 7\n'
        'kafka_consumer_in_flight_messages{service="TXNPROC",topic="transactions.persisted",'
        'group_id="portfolio_transaction_processing_group"} 2\n'
        'unsupported_consumer_metric{service="TXNPROC",topic="transactions.persisted",'
        'group_id="portfolio_transaction_processing_group",tenant_id="private"} 99\n',
    )

    result = _load_consumer_metrics("http://metrics.test/metrics")

    assert result["status"] == "observed"
    assert result["recognized_samples"] == 3
    assert result["filtered_samples"] == 2
    assert result["samples"] == [
        {
            "name": "kafka_consumer_in_flight_messages",
            "labels": {
                "service": "TXNPROC",
                "topic": "transactions.persisted",
                "group_id": "portfolio_transaction_processing_group",
            },
            "value": 2,
        }
    ]


@pytest.mark.parametrize("private_label", ["tenant_id", "transaction_id", "unsupported_label"])
@pytest.mark.parametrize(
    ("service", "topic", "group"),
    [
        ("TXNPROC", "transactions.persisted", "portfolio_transaction_processing_group"),
        (
            "TXNREPLAY",
            "transactions.reprocessing.requested",
            "portfolio_transaction_replay_request_group",
        ),
    ],
)
def test_consumer_metrics_refuse_selected_scope_private_labels(
    monkeypatch: pytest.MonkeyPatch, private_label: str, service: str, topic: str, group: str
) -> None:
    _serve_consumer_metrics(
        monkeypatch,
        f'kafka_consumer_in_flight_messages{{service="{service}",topic="{topic}",'
        f'group_id="{group}",{private_label}="private"}} 1\n',
    )

    assert _load_consumer_metrics("http://metrics.test/metrics") == {
        "status": "unavailable",
        "reason": "private_or_unknown_metric_labels",
    }
