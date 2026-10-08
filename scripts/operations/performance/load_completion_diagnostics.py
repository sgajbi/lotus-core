"""Bounded read-only completion diagnostics for the isolated performance load gate."""

from __future__ import annotations

import json
import math
import multiprocessing
import os
import re
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import ExitStack
from datetime import UTC, datetime
from typing import Any

import requests  # type: ignore[import-untyped]
from portfolio_common.connection_security import build_kafka_connection_config
from portfolio_common.database_runtime_profile import DatabasePoolMode
from portfolio_common.db import create_sync_database_engine
from prometheus_client.parser import text_string_to_metric_families

from scripts.operations.performance.load_diagnostic_capture import (
    DiagnosticCapture,
    DiagnosticScopeSlot,
    bound_diagnostic_evidence,
    read_diagnostic_scope,
)
from scripts.operations.transaction_processing_load_support import LOAD_TENANT_ID

DIAGNOSTIC_BUDGET_SECONDS = 6.0
DIAGNOSTIC_MAX_BYTES = 32768
DIAGNOSTIC_METRICS_INPUT_MAX_BYTES = 1024 * 1024
DIAGNOSTIC_MAX_ROWS = 20
DIAGNOSTIC_IO_SECONDS = 0.5
_OFFSET_SCOPES = (
    ("transactions.raw.received", "persistence_group_transactions"),
    ("transactions.persisted", "portfolio_transaction_processing_group"),
    ("transactions.reprocessing.requested", "portfolio_transaction_replay_request_group"),
)
_CONSUMER_METRIC_SCOPES = frozenset(
    {
        ("TXNPROC", "transactions.persisted", "portfolio_transaction_processing_group"),
        (
            "TXNREPLAY",
            "transactions.reprocessing.requested",
            "portfolio_transaction_replay_request_group",
        ),
    }
)

# Export only known schema identifiers and grammar, never arbitrary SQL values/names.
_STATEMENT_WORDS = frozenset(
    "select update insert into delete from join where and or not null is set values returning "
    "for share key no skip locked order by asc desc limit on conflict do nothing as "
    "transactions portfolios instruments cashflows position_history outbox_events processed_events "
    "portfolio_id transaction_id security_id tenant_id quantity gross_cost net_cost status "
    "transaction_date cash_accounts instrument_id pg_advisory_xact_lock "
    "varchar numeric integer bigint uuid timestamp timestamptz boolean".split()
)


def _statement_structure(query: Any) -> dict[str, Any]:
    """Fail closed on ambiguous syntax; whitelist tokens cannot reveal SQL literals."""
    if not isinstance(query, str) or not query or len(query) >= 2048:
        return {"status": "unavailable", "reason": "missing_or_truncated_statement"}
    # Dollar quotes, comments and escape strings need a parser; do not guess their extent.
    parameterized = re.sub(r"\$[1-9]\d*(?![\w])", " ? ", query)
    if any(marker in parameterized for marker in ("$", "--", "/*", "\\")):
        return {"status": "unavailable", "reason": "unsupported_statement_syntax"}
    scrubbed = re.sub(r"'(?:''|[^'])*'", " ? ", parameterized)
    scrubbed = re.sub(
        r'"(?:""|[^"])*"',
        lambda match: (
            match.group()[1:-1].lower()
            if match.group()[1:-1].lower() in _STATEMENT_WORDS
            else " ? "
        ),
        scrubbed,
    )
    if "'" in scrubbed or '"' in scrubbed:
        return {"status": "unavailable", "reason": "unbalanced_statement_quotes"}
    tokens = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|[^\s]", scrubbed)
    operation = tokens[0].lower() if tokens else ""
    if operation not in {"select", "update", "insert", "delete"}:
        return {"status": "unavailable", "reason": "unsupported_statement_operation"}
    structure = " ".join(
        token.lower() if token.lower() in _STATEMENT_WORDS or token in "(),.=<>:*" else "?"
        for token in tokens
    )
    return {
        "status": "observed",
        "operation": operation,
        "structure": structure[:1024],
        "policy": "whitelisted_schema_and_grammar_all_other_tokens_redacted",
    }


def _new_diagnostic_child(
    database_url: str,
    metrics_url: str,
    kafka_bootstrap_servers: str,
    scope: dict[str, Any],
    *,
    idle_controls: tuple[Any, ...] | None = None,
) -> tuple[Any, Any, Any]:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    try:
        process = context.Process(
            target=_diagnostic_worker if idle_controls is None else _idle_diagnostic_worker,
            args=(sender, database_url, metrics_url, kafka_bootstrap_servers, scope)
            + (idle_controls or ()),
            daemon=True,
        )
    except Exception:
        for pipe in (sender, receiver):
            try:
                pipe.close()
            except Exception:
                pass  # Preserve construction refusal; no child was created.
        raise
    return process, receiver, sender


def start_load_completion_diagnostics(
    *,
    database_url: str,
    metrics_url: str,
    kafka_bootstrap_servers: str,
    scope: dict[str, Any],
    isolated_runtime: bool,
    idle_seconds: float,
) -> DiagnosticCapture | None:
    """Pre-arm outside replay clocks; native process startup has no hard latency bound."""
    if not isolated_runtime:
        return None
    context = multiprocessing.get_context("spawn")
    request_event, cancel_event, ready_event = (context.Event() for _ in range(3))
    slot = DiagnosticScopeSlot(scope)
    try:
        process, receiver, sender = _new_diagnostic_child(
            database_url,
            metrics_url,
            kafka_bootstrap_servers,
            scope,
            idle_controls=(request_event, cancel_event, ready_event, idle_seconds, slot.descriptor),
        )
    except Exception:
        slot.close()
        raise
    return DiagnosticCapture(
        process=process,
        receiver=receiver,
        sender=sender,
        public_scope={
            key: value
            for key, value in scope.items()
            if key not in {"submitted_ids", "ingestion_job_ids", "compose_file"}
        },
        stop_process=_stop_diagnostic_process,
        budget_seconds=DIAGNOSTIC_BUDGET_SECONDS,
        max_bytes=DIAGNOSTIC_MAX_BYTES,
        request_event=request_event,
        cancel_event=cancel_event,
        ready_event=ready_event,
        idle_seconds=idle_seconds,
        scope_slot=slot,
    )


def collect_load_completion_diagnostics(
    *,
    database_url: str,
    metrics_url: str,
    kafka_bootstrap_servers: str,
    scope: dict[str, Any],
    isolated_runtime: bool,
) -> dict[str, Any]:
    """Bound all probes, including blocked I/O, outside the enforcing drain deadline."""
    if not isolated_runtime:
        return {"status": "unavailable", "reason": "managed_isolated_runtime_required"}
    public_scope = {
        key: value
        for key, value in scope.items()
        if key not in {"submitted_ids", "ingestion_job_ids", "compose_file"}
    }
    process, receiver, sender = _new_diagnostic_child(
        database_url, metrics_url, kafka_bootstrap_servers, scope
    )
    result: dict[str, Any]
    try:
        process.start()
        sender.close()
        if not receiver.poll(DIAGNOSTIC_BUDGET_SECONDS):
            result = {"status": "budget_exhausted", "scope": public_scope}
        else:
            encoded = receiver.recv_bytes(DIAGNOSTIC_MAX_BYTES)
            result = json.loads(encoded)
    except Exception as exc:
        result = {"status": "unavailable", "reason": type(exc).__name__, "scope": public_scope}
    finally:
        cleanup = _stop_diagnostic_process(process)
        for pipe in (sender, receiver):
            try:
                pipe.close()
            except Exception as exc:
                cleanup.setdefault("errors", []).append(type(exc).__name__)
    result["child_cleanup"] = cleanup
    return bound_diagnostic_evidence(result, DIAGNOSTIC_MAX_BYTES)


def _stop_diagnostic_process(process: Any) -> dict[str, Any]:
    """Confirm absence of the child we created; cleanup failures are never enforcing failures."""
    errors = []
    if process.pid is None:
        try:
            process.close()
        except Exception as exc:
            errors.append(type(exc).__name__)
        return {"status": "not_started", "errors": errors}
    for stop in (process.terminate, process.kill):
        try:
            if process.is_alive():
                stop()
            process.join(timeout=0.2)
            if not process.is_alive():
                try:
                    process.close()
                except Exception as exc:
                    errors.append(type(exc).__name__)
                return {"status": "stopped", "errors": errors}
        except Exception as exc:
            errors.append(type(exc).__name__)
    return {"status": "unconfirmed", "errors": errors}


def _idle_diagnostic_worker(
    sender: Any,
    database_url: str,
    metrics_url: str,
    kafka_bootstrap_servers: str,
    scope: dict[str, Any],
    request_event: Any,
    cancel_event: Any,
    ready_event: Any,
    idle_seconds: float,
    scope_descriptor: dict[str, Any] | None = None,
) -> None:
    """No probes until a one-shot request; expired/unused preparations cannot probe."""
    try:
        ready_event.set()
        if request_event.wait(idle_seconds) and not cancel_event.is_set():
            if scope_descriptor is not None:
                try:
                    scope, deadline = read_diagnostic_scope(scope_descriptor, scope)
                except Exception as exc:
                    sender.send_bytes(
                        json.dumps({"status": "unavailable", "reason": type(exc).__name__}).encode()
                    )
                    return
                _diagnostic_worker(
                    sender,
                    database_url,
                    metrics_url,
                    kafka_bootstrap_servers,
                    scope,
                    cancel_event,
                    deadline,
                )
                return
            _diagnostic_worker(
                sender, database_url, metrics_url, kafka_bootstrap_servers, scope, cancel_event
            )
    finally:
        sender.close()


def _diagnostic_worker(
    sender: Any,
    database_url: str,
    metrics_url: str,
    kafka_bootstrap_servers: str,
    scope: dict[str, Any],
    cancel_event: Any = None,
    request_deadline: float | None = None,
) -> None:
    """No writes/group join/business scans; export only whitelisted SQL structure."""
    public_scope = {
        key: value
        for key, value in scope.items()
        if key not in {"submitted_ids", "ingestion_job_ids", "compose_file"}
    }
    evidence: dict[str, Any] = {
        "status": "observed",
        "scope": public_scope,
        "observed_at": datetime.now(UTC).isoformat(),
        "probes": {},
    }
    deadline = (
        time.monotonic() + DIAGNOSTIC_BUDGET_SECONDS - 1
        if request_deadline is None
        else request_deadline
    )
    for name, probe in (
        ("managed_worker", lambda: _load_managed_worker_identity(scope)),
        ("database", lambda: _load_database_diagnostics(database_url, scope)),
        ("ptp_metrics", lambda: _load_consumer_metrics(metrics_url)),
        ("processing_phases", lambda: _load_processing_phases(scope, evidence["probes"])),
        ("consumer_offsets", lambda: _load_consumer_offsets(kafka_bootstrap_servers, deadline)),
    ):
        if time.monotonic() >= deadline or (cancel_event is not None and cancel_event.is_set()):
            evidence["probes"][name] = {"status": "budget_exhausted"}
            continue
        try:
            evidence["probes"][name] = probe()
        except Exception as exc:
            evidence["probes"][name] = {"status": "unavailable", "reason": type(exc).__name__}
    # Reserve space inside the existing limit for parent timing and cleanup. The parent
    # still independently bounds its actual envelope; this is not a larger byte budget.
    evidence = bound_diagnostic_evidence(evidence, DIAGNOSTIC_MAX_BYTES - 2048)
    encoded = json.dumps(evidence, default=str).encode()
    try:
        sender.send_bytes(encoded)
    finally:
        sender.close()


def _load_database_diagnostics(database_url: str, scope: dict[str, Any]) -> dict[str, Any]:
    from psycopg2.extras import RealDictCursor

    engine = _diagnostic_database_engine(database_url)
    try:
        connection = engine.raw_connection()
        try:
            connection.set_session(readonly=True, autocommit=True)
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '100ms'")
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT tenant_id FROM portfolios WHERE portfolio_id=%s",
                    (scope["portfolio_id"],),
                )
                owner = cursor.fetchone()
                if owner is None or owner["tenant_id"] != LOAD_TENANT_ID:
                    return {"status": "unavailable", "reason": "governed_portfolio_owner_mismatch"}
            return _load_database_probes(connection, scope, RealDictCursor)
        finally:
            connection.close()
    finally:
        engine.dispose()


def _diagnostic_database_engine(database_url: str) -> Any:
    # Called only in the private diagnostic child. Restore even for factory/security refusal,
    # so direct unit calls cannot leak diagnostic limits into their parent test environment.
    limits = {
        "LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS": "2",
        "LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS": "500",
    }
    previous = {key: os.environ.get(key) for key in limits}
    try:
        os.environ.update(limits)
        return create_sync_database_engine(
            runtime_identity="performance-load-gate",
            database_url=database_url,
            pool_mode=DatabasePoolMode.NULL,
        )
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_database_probes(
    connection: Any, scope: dict[str, Any], cursor_factory: Any
) -> dict[str, Any]:
    ids, jobs = scope["submitted_ids"], scope["ingestion_job_ids"]
    probes = {
        "exact_prefix_counts": (
            """SELECT count(*) AS transaction_count,
            count(*) FILTER (WHERE gross_cost IS NOT NULL AND net_cost IS NOT NULL
              AND transaction_fx_rate IS NOT NULL) AS cost_count,
            (SELECT count(*) FROM cashflows WHERE portfolio_id=%s AND transaction_id=ANY(%s))
              AS cashflow_count,
            (SELECT count(*) FROM position_history WHERE portfolio_id=%s
              AND transaction_id=ANY(%s)) AS position_count,
            (SELECT count(*) FROM processed_events WHERE portfolio_id=%s AND tenant_id=%s
              AND service_name='portfolio-transaction-processing') AS portfolio_aggregate_claims
            FROM transactions WHERE portfolio_id=%s AND transaction_id=ANY(%s)""",
            (
                scope["portfolio_id"],
                ids,
                scope["portfolio_id"],
                ids,
                scope["portfolio_id"],
                LOAD_TENANT_ID,
                scope["portfolio_id"],
                ids,
            ),
        ),
        "outbox_lifecycle": (
            """SELECT left(topic,128) AS topic, left(status,128) AS status,
            left(last_failure_reason_code,128) AS failure_reason_code, count(*) AS count,
            extract(epoch FROM (now()-min(created_at))) AS oldest_age_seconds
            FROM outbox_events WHERE payload->>'portfolio_id'=%s
              AND payload->>'transaction_id'=ANY(%s)
            GROUP BY topic,status,last_failure_reason_code
            ORDER BY count(*) DESC LIMIT 20""",
            (scope["portfolio_id"], ids),
        ),
        "ingestion_lifecycle": (
            """SELECT left(status,128) AS status,
            left(failure_code,128) AS failure_code, count(*) AS count,
            sum(accepted_count) AS accepted_count,
            extract(epoch FROM (now()-min(submitted_at))) AS oldest_age_seconds
            FROM ingestion_jobs WHERE tenant_id=%s AND job_id=ANY(%s)
            GROUP BY status,failure_code ORDER BY count(*) DESC LIMIT 20""",
            (LOAD_TENANT_ID, jobs),
        ),
        "consumer_rejections": (
            """SELECT left(original_topic,128) AS topic,
            left(consumer_group,128) AS consumer_group, left(error_reason_code,128) AS reason_code,
            count(*) AS count FROM consumer_dlq_events WHERE tenant_id=%s
              AND ingestion_job_id=ANY(%s) GROUP BY original_topic,consumer_group,error_reason_code
            ORDER BY count(*) DESC LIMIT 20""",
            (LOAD_TENANT_ID, jobs),
        ),
        "runtime_db_waits": (
            """SELECT pid, backend_start, datid AS database_oid,
            CASE WHEN application_name=ANY(%s) THEN application_name ELSE 'external_blocker' END
              AS application_name,
            state, wait_event_type, wait_event,
            extract(epoch FROM (now()-xact_start)) AS transaction_age_seconds,
            extract(epoch FROM (now()-query_start)) AS query_age_seconds,
            backend_xid::text AS backend_xid,
            to_jsonb(pg_stat_activity)->>'query_id' AS query_id,
            left(query,2048) AS private_statement,
            (pg_blocking_pids(pid))[1:10] AS blocking_pids FROM pg_stat_activity
            WHERE datname=current_database() AND (application_name=ANY(%s) OR pid IN (
              SELECT unnest(pg_blocking_pids(pid)) FROM pg_stat_activity
              WHERE datname=current_database() AND application_name=ANY(%s)))
            ORDER BY xact_start NULLS LAST LIMIT 20""",
            tuple(
                ["portfolio-transaction-processing", "persistence-service", "outbox-dispatcher"]
                for _ in range(3)
            ),
        ),
        "runtime_db_locks": (
            """WITH activity AS MATERIALIZED (
              SELECT pid, backend_start, application_name, pg_blocking_pids(pid) AS blockers
              FROM pg_stat_activity WHERE datname=current_database()),
            edges AS (
              SELECT w.pid AS waiter_pid, w.backend_start AS waiter_backend_start,
                b.pid AS blocker_pid, b.backend_start AS blocker_backend_start
              FROM activity w CROSS JOIN LATERAL unnest(w.blockers) AS p(pid)
              JOIN activity b ON b.pid=p.pid WHERE w.application_name=ANY(%s))
            SELECT a.pid, a.backend_start, l.locktype, l.database AS database_oid,
            l.relation AS relation_oid, l.mode, l.granted, l.transactionid::text AS transaction_id,
            l.classid, l.objid, l.objsubid, edge.waiter_pid, edge.waiter_backend_start,
            edge.blocker_pid, edge.blocker_backend_start,
            CASE WHEN edge.blocker_pid IS NULL THEN 'runtime_sample'
              WHEN l.granted THEN 'blocker_head' ELSE 'waiting_edge' END AS blocking_role,
            count(*) OVER() AS total_rows FROM pg_locks l
            JOIN activity a ON a.pid=l.pid
            LEFT JOIN LATERAL (SELECT e.* FROM edges e WHERE
              (l.pid=e.waiter_pid AND NOT l.granted) OR
              (l.pid=e.blocker_pid AND l.granted AND EXISTS (
                SELECT 1 FROM pg_locks w WHERE w.pid=e.waiter_pid AND NOT w.granted
                AND ROW(l.locktype,l.database,l.relation,l.page,l.tuple,l.virtualxid,
                  l.transactionid,l.classid,l.objid,l.objsubid) IS NOT DISTINCT FROM
                    ROW(w.locktype,w.database,w.relation,w.page,w.tuple,w.virtualxid,
                      w.transactionid,w.classid,w.objid,w.objsubid)))) edge ON true
            WHERE a.application_name=ANY(%s) OR edge.blocker_pid IS NOT NULL
            ORDER BY (edge.blocker_pid IS NULL), edge.waiter_pid,
              l.granted DESC, a.backend_start, a.pid, l.locktype LIMIT 21""",
            tuple(
                ["portfolio-transaction-processing", "persistence-service", "outbox-dispatcher"]
                for _ in range(2)
            ),
        ),
    }
    result: dict[str, Any] = {}
    for name, (query, params) in probes.items():
        if name in {"exact_prefix_counts", "outbox_lifecycle"} and not ids:
            result[name] = {"status": "unavailable", "reason": "submitted_source_ids_missing"}
            continue
        if name in {"ingestion_lifecycle", "consumer_rejections"} and not jobs:
            result[name] = {"status": "unavailable", "reason": "acknowledgement_job_ids_missing"}
            continue
        try:
            with connection.cursor(cursor_factory=cursor_factory) as cursor:
                cursor.execute(query, params)
                fetched = [dict(row) for row in cursor.fetchmany(DIAGNOSTIC_MAX_ROWS + 1)]
            if name == "runtime_db_locks":
                _qualify_lock_edges(fetched, result.get("runtime_db_waits", {}).get("rows", []))
                fetched.sort(
                    key=lambda row: (
                        row.get("edge_identity_status") != "observed",
                        row.get("waiter_pid") or row.get("pid") or 0,
                        row.get("blocking_role") != "blocker_head",
                    )
                )
            rows = fetched[:DIAGNOSTIC_MAX_ROWS]
            totals = [row.pop("total_rows") for row in rows if "total_rows" in row]
            if name == "runtime_db_waits":
                for row in rows:
                    row["statement"] = _statement_structure(row.pop("private_statement", None))
                    row["exact_await"] = "MISSING"
            if name.startswith("runtime_db_"):
                for row in rows:
                    row["backend_identity_status"] = (
                        "observed" if row.get("pid") and row.get("backend_start") else "missing"
                    )
            result[name] = {
                "status": "observed",
                "rows": rows,
                "row_limit": DIAGNOSTIC_MAX_ROWS,
                "truncated": len(fetched) > DIAGNOSTIC_MAX_ROWS
                or any(total > DIAGNOSTIC_MAX_ROWS for total in totals),
                "observed_total_rows": max(totals) if totals else None,
                "scope": "isolated_runtime" if name.startswith("runtime_db_") else "submitted_ids",
            }
        except Exception as exc:
            connection.rollback()
            result[name] = {"status": "unavailable", "reason": type(exc).__name__}
    return result


def _qualify_lock_edges(rows: list[dict[str, Any]], waits: list[dict[str, Any]]) -> None:
    """Never associate a reused PID with a previously observed backend birth."""
    births = {row["pid"]: row.get("backend_start") for row in waits if row.get("pid")}
    for row in rows:
        if row.get("blocking_role") not in {"blocker_head", "waiting_edge"}:
            continue
        identities = [
            (row.get(role + "_pid"), row.get(role + "_backend_start"))
            for role in ("waiter", "blocker")
        ]
        if any(pid in births and births[pid] != birth for pid, birth in identities):
            row["edge_identity_status"] = "stale_birth"
            row["blocking_role"] = "unqualified"
        elif all(pid and birth and births.get(pid) == birth for pid, birth in identities):
            row["edge_identity_status"] = "observed"
        else:
            row["edge_identity_status"] = "missing_birth_observation"
        row["exact_await"] = "MISSING"


def _load_managed_worker_identity(scope: dict[str, Any]) -> dict[str, Any]:
    """Observe only the exact managed service container, not an inferred Python/Kafka worker PID."""
    project, compose_file = scope.get("runtime"), scope.get("compose_file")
    port = scope.get("metrics_port")
    if (
        not isinstance(project, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", project)
        or not compose_file
        or type(port) is not int
    ):
        return {"status": "missing", "reason": "managed_identity_missing"}
    service = "portfolio_transaction_processing_service"
    # Plain Docker avoids a Compose plugin descendant retaining captured subprocess pipes.
    command = [
        "docker",
        "ps",
        "--no-trunc",
        "--quiet",
        "--filter",
        f"label=com.docker.compose.project={project}",
        "--filter",
        f"label=com.docker.compose.service={service}",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, check=True, timeout=DIAGNOSTIC_IO_SECONDS
    )
    identifiers = result.stdout.split()
    if len(identifiers) != 1 or not re.fullmatch(r"[a-f0-9]{64}", identifiers[0]):
        return {"status": "missing", "reason": "container_identity_ambiguous"}
    template = (
        "[{{json .Id}},{{json .Created}},{{json .State.StartedAt}},{{json .State.Pid}},"
        '{{json (index .Config.Labels "com.docker.compose.project")}},'
        '{{json (index .Config.Labels "com.docker.compose.service")}},'
        '{{json (index .NetworkSettings.Ports "8085/tcp")}}]'
    )
    result = subprocess.run(
        ["docker", "inspect", "--format", template, identifiers[0]],
        capture_output=True,
        text=True,
        check=True,
        timeout=DIAGNOSTIC_IO_SECONDS,
    )
    if len(result.stdout) > 2048:
        return {"status": "unavailable", "reason": "identity_byte_budget"}
    values = json.loads(result.stdout)
    if len(values) != 7 or values[4:6] != [project, service] or values[0] != identifiers[0]:
        return {"status": "unavailable", "reason": "container_scope_mismatch"}
    if not isinstance(values[6], list) or not any(
        isinstance(binding, dict) and binding.get("HostPort") == str(port) for binding in values[6]
    ):
        return {"status": "unavailable", "reason": "metrics_port_mismatch"}
    if (
        type(values[3]) is not int
        or values[3] <= 0
        or not all(isinstance(value, str) and 0 < len(value) <= 64 for value in values[1:3])
    ):
        return {"status": "missing", "reason": "container_birth_identity_missing"}
    return {
        "status": "observed",
        "observed_at": datetime.now(UTC).isoformat(),
        "container_id": values[0],
        "created_at": values[1],
        "started_at": values[2],
        "container_init_pid": values[3],
        "service": service,
        "metrics_port": port,
        "worker_pid": "MISSING",
        "exact_await": "MISSING",
    }


def _load_consumer_metrics(metrics_url: str) -> dict[str, Any]:
    names = {
        "kafka_consumer_in_flight_messages",
        "kafka_consumer_backlog_pressure_total",
        "kafka_consumer_partition_lag_messages",
    }
    samples: list[dict[str, Any]] = []
    with requests.get(metrics_url, timeout=DIAGNOSTIC_IO_SECONDS, stream=True) as response:
        response.raise_for_status()
        raw = bytearray()
        for chunk in response.iter_content(4096):
            raw.extend(chunk)
            if len(raw) > DIAGNOSTIC_METRICS_INPUT_MAX_BYTES:
                return {"status": "byte_budget_exhausted", "reason": "metrics_input_limit"}
    truncated = False
    recognized = 0
    filtered = 0
    try:
        for family in text_string_to_metric_families(raw.decode()):
            for sample in family.samples:
                if sample.name not in names:
                    continue
                recognized += 1
                if tuple(sample.labels.get(k) for k in ("service", "topic", "group_id")) not in (
                    _CONSUMER_METRIC_SCOPES
                ):
                    filtered += 1
                    continue
                if not _public_consumer_labels(sample.labels):
                    return {"status": "unavailable", "reason": "private_or_unknown_metric_labels"}
                if not math.isfinite(sample.value):
                    return {"status": "unavailable", "reason": "nonfinite_metric_value"}
                if len(samples) == DIAGNOSTIC_MAX_ROWS:
                    truncated = True
                    continue
                samples.append(
                    {"name": sample.name, "labels": dict(sample.labels), "value": sample.value}
                )
    except (ValueError, UnicodeError):
        return {"status": "unavailable", "reason": "malformed_metrics"}
    result = {
        "status": "observed" if samples else "unavailable",
        "scope": "runtime_aggregate_not_prefix",
        "lag_semantics": "cached_high_watermark_minus_committed",
        "truncated": truncated,
        "input_byte_limit": DIAGNOSTIC_METRICS_INPUT_MAX_BYTES,
        "reason": None if samples else "no_matching_consumer_metric_samples",
        "recognized_samples": recognized,
        "filtered_samples": filtered,
    }
    if samples:
        result["samples"] = samples
    return result


def _processing_transport_script(*, enable: bool) -> str:
    """Keep remote filesystem operations within one exclusively owned private directory."""
    header = """import os, stat, sys, tempfile
from pathlib import Path
root = Path(tempfile.gettempdir()) / 'lotus-load-uow'
def require_private(meta, directory):
    kind = stat.S_ISDIR(meta.st_mode) if directory else stat.S_ISREG(meta.st_mode)
    mode = 0o700 if directory else 0o600
    if not kind or meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != mode:
        raise PermissionError('processing_diagnostic_transport_not_private')
"""
    action = (
        """os.mkdir(root, 0o700)
directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
descriptor = None
try:
    require_private(os.fstat(directory), True)
    descriptor = os.open('enable.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
    require_private(os.fstat(descriptor), False)
    with os.fdopen(descriptor, 'w') as stream:
        descriptor = None
        stream.write(sys.argv[1])
finally:
    if descriptor is not None:
        os.close(descriptor)
    os.close(directory)
"""
        if enable
        else """directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
descriptor = None
try:
    require_private(os.fstat(directory), True)
    descriptor = os.open('snapshot.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    require_private(os.fstat(descriptor), False)
    with os.fdopen(descriptor, 'rb') as stream:
        descriptor = None
        sys.stdout.buffer.write(stream.read(16385))
finally:
    if descriptor is not None:
        os.close(descriptor)
    os.close(directory)
"""
    )
    return header + action


def enable_managed_processing_phases(scope: dict[str, Any]) -> dict[str, Any]:
    """Opt the exact disposable load container into a private transient snapshot."""
    if scope.get("tenant_id") != LOAD_TENANT_ID or scope.get("portfolio_id") != "PERF_BALANCED_V1":
        return {"status": "unavailable", "reason": "governed_phase_scope_required"}
    try:
        identity = _load_managed_worker_identity(scope)
        if identity.get("status") != "observed":
            return identity
        generation = uuid.uuid4().hex
        config = {
            "generation": generation,
            "tenant_id": LOAD_TENANT_ID,
            "portfolio_id": "PERF_BALANCED_V1",
            "created_at": time.time(),
        }
        script = _processing_transport_script(enable=True)
        subprocess.run(
            [
                "docker",
                "exec",
                identity["container_id"],
                "python",
                "-c",
                script,
                json.dumps(config),
            ],
            check=True,
            capture_output=True,
            timeout=DIAGNOSTIC_IO_SECONDS,
        )
        return {
            "status": "enabled",
            "generation": generation,
            "container_id": identity["container_id"],
            "created_at": identity["created_at"],
            "started_at": identity["started_at"],
        }
    except Exception as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}


def _load_processing_phases(scope: dict[str, Any], probes: dict[str, Any]) -> dict[str, Any]:
    """Read only the owned snapshot; stale backend/run generations never become awaits."""
    if scope.get("tenant_id") != LOAD_TENANT_ID or scope.get("portfolio_id") != "PERF_BALANCED_V1":
        return {"status": "unavailable", "reason": "governed_phase_scope_required"}
    generation = scope.get("phase_generation")
    worker = probes.get("managed_worker", {})
    if (
        not isinstance(generation, str)
        or not re.fullmatch(r"[a-f0-9]{32}", generation)
        or worker.get("status") != "observed"
    ):
        return {"status": "unavailable", "reason": "phase_capture_not_enabled"}
    if (
        worker.get("container_id") != scope.get("phase_container_id")
        or not scope.get("phase_container_started_at")
        or worker.get("started_at") != scope.get("phase_container_started_at")
    ):
        return {"status": "unavailable", "reason": "phase_container_generation_mismatch"}
    result = subprocess.run(
        [
            "docker",
            "exec",
            worker["container_id"],
            "python",
            "-c",
            _processing_transport_script(enable=False),
        ],
        check=True,
        capture_output=True,
        timeout=DIAGNOSTIC_IO_SECONDS,
    )
    if len(result.stdout) > 16384:
        return {"status": "unavailable", "reason": "phase_snapshot_byte_budget"}
    payload = json.loads(result.stdout)
    if payload.get("run_generation") != generation:
        return {"status": "unavailable", "reason": "phase_run_generation_mismatch"}
    if not 0 <= time.time() - payload.get("captured_at", 0) < 120:
        return {"status": "unavailable", "reason": "phase_snapshot_stale"}
    rows = payload.get("rows", [])
    if not isinstance(rows, list) or len(rows) > DIAGNOSTIC_MAX_ROWS:
        return {"status": "unavailable", "reason": "phase_row_budget"}
    waits = probes.get("database", {}).get("runtime_db_waits", {}).get("rows", [])
    qualified, admission = _processing_phase_admission(rows, payload, waits)
    return {
        "status": "observed" if qualified else "unavailable",
        "reason": None if qualified else "no_birth_qualified_active_phase",
        "rows": qualified,
        "admission": admission,
        "truncated": bool(payload.get("truncated")),
        "row_limit": 20,
    }


_PHASE_REJECTION_REASONS = frozenset(
    {
        "invalid_row",
        "inactive",
        "backend_missing",
        "backend_identity_invalid",
        "backend_not_in_observed_sample",
        "backend_identity_ambiguous",
        "invalid_phase_metadata",
        "duplicate_pid",
    }
)
_PHASE_COUNTER_MAX = 2**31 - 1


def _phase_counter(value: Any) -> dict[str, Any]:
    """Missing or malformed supporting counters never become zero or row authority."""
    if value is None:
        return {"status": "missing", "value": None}
    if type(value) is not int or not 0 <= value <= _PHASE_COUNTER_MAX:
        return {"status": "invalid", "value": None}
    return {"status": "observed", "value": value}


def _phase_candidate_rejection(row: Any, waits: list[dict[str, Any]]) -> str | None:
    if not isinstance(row, dict):
        return "invalid_row"
    if row.get("active") is not True:
        return "inactive"
    backend = row.get("backend")
    if not isinstance(backend, dict):
        return "backend_missing"
    identity = _diagnostic_backend_identity(backend)
    if identity is None:
        return "backend_identity_invalid"
    matches = sum(_diagnostic_backend_identity(w) == identity for w in waits)
    if matches == 0:
        return "backend_not_in_observed_sample"
    return "backend_identity_ambiguous" if matches > 1 else None


def _phase_admission_counts(
    candidate: int, active: int, admitted: int, reasons: dict[str, int]
) -> dict[str, Any]:
    """Closed mutually exclusive first-rejection counts, not runtime failure causes."""
    counts = (candidate, active, admitted, *reasons.values())
    if any(type(n) is not int or not 0 <= n <= DIAGNOSTIC_MAX_ROWS for n in counts):
        raise ValueError("phase_admission_count_invalid")
    if set(reasons) - _PHASE_REJECTION_REASONS:
        raise ValueError("phase_admission_category_invalid")
    if not admitted <= active <= candidate or sum(reasons.values()) != candidate - admitted:
        raise ValueError("phase_admission_count_mismatch")
    if active != candidate - reasons.get("inactive", 0) - reasons.get("invalid_row", 0):
        raise ValueError("phase_admission_active_count_mismatch")
    return {
        "schema_version": "processing-phase-admission.v1",
        "candidate_count": candidate,
        "active_count": active,
        "admitted_count": admitted,
        "rejected_count": candidate - admitted,
        "rejected_by_reason": reasons,
        "scope": "bounded_snapshot_rows_not_whole_worker",
    }


def _processing_phase_admission(
    rows: list[Any], payload: dict[str, Any], waits: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    qualified = []
    reasons: dict[str, int] = {}
    for row in rows:
        reason = _phase_candidate_rejection(row, waits)
        projected = None if reason else _project_processing_phase(row, payload, waits)
        if reason is None and projected is None:
            reason = "invalid_phase_metadata"
        if reason is not None:
            reasons[reason] = reasons.get(reason, 0) + 1
        elif projected is not None:
            qualified.append(projected)
    # Preserve the existing fail-closed ambiguity rule; never pick one by row order.
    pids = [row["backend"]["pid"] for row in qualified]
    admitted = [row for row in qualified if pids.count(row["backend"]["pid"]) == 1]
    duplicate_count = len(qualified) - len(admitted)
    if duplicate_count:
        reasons["duplicate_pid"] = duplicate_count
    active = sum(isinstance(row, dict) and row.get("active") is True for row in rows)
    summary = _phase_admission_counts(len(rows), active, len(admitted), reasons)
    summary["worker_counters"] = {
        key: _phase_counter(payload.get(key)) for key in ("capture_errors", "callback_failures")
    }
    return admitted, summary


def _diagnostic_backend_identity(value: Any) -> tuple[int, datetime, int] | None:
    if not isinstance(value, dict):
        return None
    pid, oid, birth = value.get("pid"), value.get("database_oid"), value.get("backend_start")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if not isinstance(oid, int) or isinstance(oid, bool) or oid <= 0 or not isinstance(birth, str):
        return None
    try:
        parsed = datetime.fromisoformat(birth)
        return (pid, parsed.astimezone(UTC), oid) if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _diagnostic_hex(value: Any, size: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[a-f0-9]{{{size}}}", value) is not None


def _project_processing_phase(
    row: Any, payload: dict[str, Any], waits: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("active") is not True:
        return None
    backend = row.get("backend")
    if not isinstance(backend, dict):
        return None
    identity = _diagnostic_backend_identity(backend)
    if identity is None or sum(_diagnostic_backend_identity(w) == identity for w in waits) != 1:
        return None
    if not _diagnostic_hex(row.get("generation"), 32) or not _diagnostic_hex(
        row.get("delivery_hash"), 64
    ):
        return None
    repair_hash = row.get("repair_delivery_hash")
    if repair_hash is not None and not _diagnostic_hex(repair_hash, 64):
        return None
    if row.get("phase") not in {
        "uow_enter",
        "idempotency",
        "repair_qualification",
        "first_publication_qualification",
        "cost",
        "position",
        "cashflow",
        "readiness",
        "commit",
        "source_cut_flush",
        "durable_commit",
        "rollback",
        "session_close",
        "finished",
    }:
        return None
    if type(row.get("worker_pid")) is not int or row["worker_pid"] != payload.get("worker_pid"):
        return None
    task = row.get("task_identity")
    if not isinstance(task, str) or not re.fullmatch(r"0x[a-f0-9]{1,16}", task):
        return None
    elapsed = payload.get("captured_monotonic", 0) - row.get("phase_started_monotonic", 0)
    if not math.isfinite(elapsed) or elapsed < 0:
        return None
    projected = {
        k: row[k]
        for k in ("generation", "worker_pid", "delivery_hash", "repair_delivery_hash", "phase")
    }
    projected.update(
        backend={k: backend[k] for k in ("pid", "backend_start", "database_oid")},
        task_identity=task,
        phase_elapsed_seconds=elapsed,
        correlation="backend_pid_birth_database_generation",
        exact_await="MISSING",
        boundary="phase_in_progress_not_python_await",
    )
    return projected


def _public_consumer_labels(labels: dict[str, str]) -> bool:
    allowed = {"service", "topic", "group_id", "partition", "reason"}
    if set(labels) - allowed:
        return False
    values = {
        "topic": {topic for topic, _ in _OFFSET_SCOPES},
        "group_id": {group for _, group in _OFFSET_SCOPES},
        "reason": {
            "max_in_flight_reached",
            "pending_buffer_capacity_reached",
            "ordering_key_busy",
            "capacity_full",
        },
    }
    return all(key not in labels or labels[key] in choices for key, choices in values.items()) and (
        "partition" not in labels or bool(re.fullmatch(r"[0-9]{1,9}", labels["partition"]))
    )


def _load_consumer_offsets(bootstrap_servers: str, deadline: float) -> dict[str, Any]:
    from confluent_kafka import Consumer, TopicPartition

    if not bootstrap_servers:
        return {"status": "unavailable", "reason": "isolated_broker_endpoint_missing"}
    connection_config = build_kafka_connection_config(
        bootstrap_servers, service_name="performance-load-gate"
    )
    result: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    with ExitStack() as cleanup:
        pending: list[tuple[Consumer, dict[str, Any], Iterator[int]]] = []
        for topic, group in _OFFSET_SCOPES:
            if time.monotonic() >= deadline:
                return {
                    "status": "budget_exhausted",
                    "partitions": result,
                    "groups": groups,
                    "group_joined": False,
                }
            consumer = Consumer(
                {
                    **connection_config,
                    "group.id": group,
                    "enable.auto.commit": False,
                    "enable.auto.offset.store": False,
                    "socket.timeout.ms": 500,
                    "allow.auto.create.topics": False,
                }
            )
            cleanup.callback(consumer.close)
            observation: dict[str, Any] = {"topic": topic, "group_id": group, "status": "observed"}
            groups.append(observation)
            try:
                metadata = consumer.list_topics(topic, timeout=DIAGNOSTIC_IO_SECONDS)
                info = metadata.topics.get(topic)
                if info is None or info.error:
                    raise ValueError("topic_metadata_unavailable")
                partition_ids = sorted(info.partitions)
                observation["total_partitions"] = len(partition_ids)
                pending.append((consumer, observation, iter(partition_ids)))
            except Exception as exc:
                observation.update(status="unavailable", reason=type(exc).__name__)
        while pending and len(result) < DIAGNOSTIC_MAX_ROWS:
            remaining: list[tuple[Consumer, dict[str, Any], Iterator[int]]] = []
            for consumer, observation, partitions in pending:
                partition = next(partitions, None)
                if partition is None:
                    continue
                if time.monotonic() >= deadline:
                    return {
                        "status": "budget_exhausted",
                        "partitions": result,
                        "groups": groups,
                        "group_joined": False,
                    }
                if len(result) == DIAGNOSTIC_MAX_ROWS:
                    remaining.append((consumer, observation, partitions))
                    break
                key = TopicPartition(observation["topic"], partition)
                try:
                    committed = consumer.committed([key], timeout=DIAGNOSTIC_IO_SECONDS)[0]
                    if time.monotonic() >= deadline:
                        return {
                            "status": "budget_exhausted",
                            "partitions": result,
                            "groups": groups,
                            "group_joined": False,
                        }
                    low, high = consumer.get_watermark_offsets(key, timeout=DIAGNOSTIC_IO_SECONDS)
                except Exception as exc:
                    observation.update(status="unavailable", reason=type(exc).__name__)
                    continue
                result.append(
                    {
                        "topic": observation["topic"],
                        "group_id": observation["group_id"],
                        "partition": partition,
                        "committed": committed.offset
                        if committed.offset >= 0 and not committed.error
                        else None,
                        "low": low,
                        "end": high,
                        "scope": "partition_not_prefix",
                        "total_partitions": observation["total_partitions"],
                    }
                )
                remaining.append((consumer, observation, partitions))
            pending = remaining
    return {
        "status": "observed" if all(g["status"] == "observed" for g in groups) else "partial",
        "partitions": result,
        "groups": groups,
        "group_joined": False,
        "row_limit": DIAGNOSTIC_MAX_ROWS,
        "truncated": sum(g.get("total_partitions", 0) for g in groups) > len(result),
        "sampling": "round_robin_across_three_groups",
    }
