"""Bounded read-only completion diagnostics for the isolated performance load gate."""

from __future__ import annotations

import json
import multiprocessing
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

import requests  # type: ignore[import-untyped]
from portfolio_common.connection_security import build_kafka_connection_config
from portfolio_common.database_runtime_profile import DatabasePoolMode
from portfolio_common.db import create_sync_database_engine
from prometheus_client.parser import text_string_to_metric_families

from scripts.operations.transaction_processing_load_support import LOAD_TENANT_ID

DIAGNOSTIC_BUDGET_SECONDS = 6.0
DIAGNOSTIC_MAX_BYTES = 32768
DIAGNOSTIC_MAX_ROWS = 20
DIAGNOSTIC_IO_SECONDS = 0.5

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
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_diagnostic_worker,
        args=(
            sender,
            database_url,
            metrics_url,
            kafka_bootstrap_servers,
            scope,
        ),
        daemon=True,
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
    return result


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


def _diagnostic_worker(
    sender: Any,
    database_url: str,
    metrics_url: str,
    kafka_bootstrap_servers: str,
    scope: dict[str, Any],
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
    deadline = time.monotonic() + DIAGNOSTIC_BUDGET_SECONDS - 1
    for name, probe in (
        ("managed_worker", lambda: _load_managed_worker_identity(scope)),
        ("database", lambda: _load_database_diagnostics(database_url, scope)),
        ("ptp_metrics", lambda: _load_consumer_metrics(metrics_url)),
        ("consumer_offsets", lambda: _load_consumer_offsets(kafka_bootstrap_servers, deadline)),
    ):
        if time.monotonic() >= deadline:
            evidence["probes"][name] = {"status": "budget_exhausted"}
            continue
        try:
            evidence["probes"][name] = probe()
        except Exception as exc:
            evidence["probes"][name] = {"status": "unavailable", "reason": type(exc).__name__}
    encoded = json.dumps(evidence, default=str).encode()
    if len(encoded) > DIAGNOSTIC_MAX_BYTES:
        encoded = json.dumps({"status": "byte_budget_exhausted", "scope": public_scope}).encode()
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
            """SELECT a.pid, a.backend_start, l.locktype, l.database AS database_oid,
            l.relation AS relation_oid, l.mode, l.granted, l.transactionid::text AS transaction_id,
            l.classid, l.objid, l.objsubid FROM pg_locks l
            JOIN pg_stat_activity a ON a.pid=l.pid
            WHERE a.datname=current_database() AND (a.application_name=ANY(%s) OR a.pid IN (
              SELECT unnest(pg_blocking_pids(pid)) FROM pg_stat_activity
              WHERE datname=current_database() AND application_name=ANY(%s)))
            ORDER BY a.pid,l.granted,l.locktype LIMIT 20""",
            tuple(
                ["portfolio-transaction-processing", "persistence-service", "outbox-dispatcher"]
                for _ in range(2)
            ),
        ),
    }
    result: dict[str, Any] = {}
    for name, (query, params) in probes.items():
        if name in {"ingestion_lifecycle", "consumer_rejections"} and not jobs:
            result[name] = {"status": "unavailable", "reason": "acknowledgement_job_ids_missing"}
            continue
        try:
            with connection.cursor(cursor_factory=cursor_factory) as cursor:
                cursor.execute(query, params)
                rows = [dict(row) for row in cursor.fetchmany(DIAGNOSTIC_MAX_ROWS)]
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
                "scope": "isolated_runtime" if name.startswith("runtime_db_") else "submitted_ids",
            }
        except Exception as exc:
            connection.rollback()
            result[name] = {"status": "unavailable", "reason": type(exc).__name__}
    return result


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
    command = ["docker", "compose", "-f", compose_file, "-p", project, "ps", "-q", service]
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
    samples = []
    with requests.get(metrics_url, timeout=DIAGNOSTIC_IO_SECONDS, stream=True) as response:
        response.raise_for_status()
        raw = bytearray()
        for chunk in response.iter_content(4096):
            raw.extend(chunk)
            if len(raw) > DIAGNOSTIC_MAX_BYTES:
                return {"status": "byte_budget_exhausted"}
    for family in text_string_to_metric_families(raw.decode()):
        for sample in family.samples:
            if (
                sample.name in names
                and sample.labels.get("service") == "portfolio-transaction-processing"
            ):
                samples.append(
                    {
                        "name": sample.name,
                        "labels": {
                            key: str(value)[:128]
                            for key, value in sample.labels.items()
                            if key in {"service", "topic", "group_id", "partition", "reason"}
                        },
                        "value": sample.value,
                    }
                )
                if len(samples) == DIAGNOSTIC_MAX_ROWS:
                    break
        if len(samples) == DIAGNOSTIC_MAX_ROWS:
            break
    return {
        "status": "observed" if samples else "unavailable",
        "samples": samples,
        "scope": "runtime_aggregate_not_prefix",
        "lag_semantics": "cached_high_watermark_minus_committed",
    }


def _load_consumer_offsets(bootstrap_servers: str, deadline: float) -> dict[str, Any]:
    from confluent_kafka import Consumer, TopicPartition

    if not bootstrap_servers:
        return {"status": "unavailable", "reason": "isolated_broker_endpoint_missing"}
    connection_config = build_kafka_connection_config(
        bootstrap_servers, service_name="performance-load-gate"
    )
    result: list[dict[str, Any]] = []
    for topic, group in (
        ("transactions.raw.received", "persistence_group_transactions"),
        ("transactions.persisted", "portfolio_transaction_processing_group"),
    ):
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
        try:
            metadata = consumer.list_topics(topic, timeout=DIAGNOSTIC_IO_SECONDS)
            info = metadata.topics.get(topic)
            if info is None or info.error:
                raise ValueError("topic_metadata_unavailable")
            partitions = sorted(info.partitions)
            for partition in partitions[: DIAGNOSTIC_MAX_ROWS // 2]:
                if time.monotonic() >= deadline:
                    return {"status": "budget_exhausted", "partitions": result}
                key = TopicPartition(topic, partition)
                committed = consumer.committed([key], timeout=DIAGNOSTIC_IO_SECONDS)[0]
                low, high = consumer.get_watermark_offsets(key, timeout=DIAGNOSTIC_IO_SECONDS)
                result.append(
                    {
                        "topic": topic,
                        "group_id": group,
                        "partition": partition,
                        "committed": committed.offset
                        if committed.offset >= 0 and not committed.error
                        else None,
                        "low": low,
                        "end": high,
                        "scope": "partition_not_prefix",
                        "total_partitions": len(partitions),
                        "sample_limit": DIAGNOSTIC_MAX_ROWS // 2,
                    }
                )
        finally:
            consumer.close()
    return {"status": "observed", "partitions": result, "group_joined": False}
