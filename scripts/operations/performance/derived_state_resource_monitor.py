"""Capture database pressure and container resource use for derived-state workloads."""

from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, TypeVar

from portfolio_common.database_runtime_identity import DATABASE_RUNTIME_IDENTITIES
from sqlalchemy import Engine, text

_UNATTRIBUTED_APPLICATION = "__unattributed__"
_UNGOVERNED_APPLICATION = "__ungoverned__"
_POSTGRES_BACKGROUND_APPLICATION = "postgres-background"
GOVERNED_DATABASE_APPLICATION_COHORTS = DATABASE_RUNTIME_IDENTITIES | {
    _POSTGRES_BACKGROUND_APPLICATION
}

_DATABASE_RESOURCE_QUERY = text(
    """
    WITH activity AS (
      SELECT
        CASE
          WHEN backend_type <> 'client backend' THEN 'postgres-background'
          WHEN nullif(btrim(application_name), '') IS NULL THEN '__unattributed__'
          WHEN application_name = ANY(:governed_application_names) THEN application_name
          ELSE '__ungoverned__'
        END AS application_name,
        state,
        xact_start,
        cardinality(pg_blocking_pids(pid)) > 0 AS is_blocked,
        EXISTS (
          SELECT 1
          FROM pg_locks waiting_lock
          WHERE waiting_lock.pid = pg_stat_activity.pid
            AND NOT waiting_lock.granted
        ) AS is_lock_waiter
      FROM pg_stat_activity
      WHERE datname = current_database()
    ),
    application_cohorts AS (
      SELECT
        application_name,
        count(*)::integer AS total_connections,
        count(*) FILTER (WHERE state = 'active')::integer AS active_connections,
        count(*) FILTER (WHERE state = 'idle in transaction')::integer
          AS idle_in_transaction_connections,
        count(*) FILTER (WHERE xact_start IS NOT NULL)::integer AS open_transactions,
        count(*) FILTER (WHERE is_lock_waiter)::integer AS lock_waiters,
        count(*) FILTER (WHERE is_blocked)::integer AS blocked_sessions,
        coalesce(
          max(extract(epoch FROM clock_timestamp() - xact_start))
            FILTER (WHERE xact_start IS NOT NULL),
          0
        ) AS oldest_open_transaction_seconds,
        coalesce(
          max(extract(epoch FROM clock_timestamp() - xact_start))
            FILTER (WHERE state = 'idle in transaction' AND xact_start IS NOT NULL),
          0
        ) AS oldest_idle_in_transaction_seconds
      FROM activity
      GROUP BY application_name
    ),
    bounded_cohorts AS (
      SELECT * FROM application_cohorts
      UNION ALL
      SELECT '__unattributed__', 0, 0, 0, 0, 0, 0, 0, 0
      WHERE NOT EXISTS (
        SELECT 1 FROM application_cohorts WHERE application_name = '__unattributed__'
      )
    ),
    totals AS (
      SELECT
        sum(total_connections)::integer AS total_connections,
        sum(active_connections)::integer AS active_connections,
        sum(idle_in_transaction_connections)::integer AS idle_in_transaction_connections,
        sum(lock_waiters)::integer AS lock_waiters,
        sum(blocked_sessions)::integer AS blocked_sessions
      FROM bounded_cohorts
    )
    SELECT
      totals.*,
      current_setting('max_connections')::integer AS max_connections,
      coalesce(
        jsonb_agg(
          jsonb_build_object(
            'application_name', bounded_cohorts.application_name,
            'total_connections', bounded_cohorts.total_connections,
            'active_connections', bounded_cohorts.active_connections,
            'idle_in_transaction_connections',
              bounded_cohorts.idle_in_transaction_connections,
            'open_transactions', bounded_cohorts.open_transactions,
            'lock_waiters', bounded_cohorts.lock_waiters,
            'blocked_sessions', bounded_cohorts.blocked_sessions,
            'oldest_open_transaction_seconds',
              bounded_cohorts.oldest_open_transaction_seconds,
            'oldest_idle_in_transaction_seconds',
              bounded_cohorts.oldest_idle_in_transaction_seconds
          ) ORDER BY bounded_cohorts.application_name
        ),
        '[]'::jsonb
      ) AS application_cohorts
    FROM totals
    CROSS JOIN bounded_cohorts
    GROUP BY
      totals.total_connections,
      totals.active_connections,
      totals.idle_in_transaction_connections,
      totals.lock_waiters,
      totals.blocked_sessions
    """
)

_OUTBOX_RESOURCE_QUERY = text(
    """
    WITH outbox_totals AS (
      SELECT
        count(*) FILTER (WHERE status = 'PENDING') AS pending_events,
        count(*) FILTER (WHERE status = 'PROCESSED') AS processed_events,
        count(*) FILTER (WHERE status = 'FAILED') AS failed_events,
        count(*) FILTER (
          WHERE status = 'PENDING'
            AND (next_attempt_at IS NULL OR next_attempt_at <= clock_timestamp())
        ) AS retry_eligible_pending_events,
        count(*) FILTER (
          WHERE status = 'PENDING' AND next_attempt_at > clock_timestamp()
        ) AS retry_waiting_pending_events,
        coalesce(
          extract(
            epoch FROM clock_timestamp() - (
              min(created_at) FILTER (WHERE status = 'PENDING')
            )
          ),
          0
        ) AS oldest_pending_age_seconds
      FROM outbox_events
    ),
    recent_outbox_events AS (
      SELECT greatest(
        extract(epoch FROM coalesce(processed_at, clock_timestamp()) - created_at),
        0
      ) AS publication_age_seconds
      FROM outbox_events
      ORDER BY id DESC
      LIMIT 10000
    ),
    publication_age AS (
      SELECT
        coalesce(percentile_cont(0.50) WITHIN GROUP (ORDER BY publication_age_seconds), 0)
          AS recent_publication_age_p50_seconds,
        coalesce(percentile_cont(0.95) WITHIN GROUP (ORDER BY publication_age_seconds), 0)
          AS recent_publication_age_p95_seconds,
        coalesce(percentile_cont(0.99) WITHIN GROUP (ORDER BY publication_age_seconds), 0)
          AS recent_publication_age_p99_seconds
      FROM recent_outbox_events
    ),
    topic_cohorts AS (
      SELECT
        aggregate_type,
        topic,
        count(*) AS created_events,
        count(*) FILTER (WHERE status = 'PENDING') AS pending_events
      FROM outbox_events
      GROUP BY aggregate_type, topic
    )
    SELECT
      outbox_totals.*,
      publication_age.*,
      topic_cohorts.aggregate_type,
      topic_cohorts.topic,
      topic_cohorts.created_events AS cohort_created_events,
      topic_cohorts.pending_events AS cohort_pending_events
    FROM outbox_totals
    CROSS JOIN publication_age
    LEFT JOIN topic_cohorts ON true
    ORDER BY topic_cohorts.aggregate_type, topic_cohorts.topic
    """
)

_MEMORY_UNIT_MULTIPLIERS = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
}
_MEMORY_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]?i?B)\s*$", re.IGNORECASE)
_ResourceValue = TypeVar("_ResourceValue", int, float)


@dataclass(frozen=True, slots=True)
class DatabaseApplicationResourceUsage:
    """Bounded PostgreSQL pressure evidence attributed to one application cohort."""

    application_name: str
    total_connections: int
    active_connections: int
    idle_in_transaction_connections: int
    open_transactions: int
    lock_waiters: int
    blocked_sessions: int
    oldest_open_transaction_seconds: float
    oldest_idle_in_transaction_seconds: float


@dataclass(frozen=True, slots=True)
class DatabaseResourceUsage:
    """One PostgreSQL capacity and lock-pressure observation."""

    total_connections: int
    active_connections: int
    idle_in_transaction_connections: int
    lock_waiters: int
    blocked_sessions: int
    max_connections: int
    connection_utilization_percent: float
    application_cohorts: tuple[DatabaseApplicationResourceUsage, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeResourceUsage:
    """One derived-state container CPU and memory observation."""

    cpu_percent: float
    memory_usage_bytes: int
    memory_limit_bytes: int
    memory_utilization_percent: float


@dataclass(frozen=True, slots=True)
class OutboxResourceUsage:
    """One durable publication backlog and age observation."""

    pending_events: int
    processed_events: int
    failed_events: int
    retry_eligible_pending_events: int
    retry_waiting_pending_events: int
    oldest_pending_age_seconds: float
    recent_publication_age_p50_seconds: float
    recent_publication_age_p95_seconds: float
    recent_publication_age_p99_seconds: float
    pending_events_by_topic: tuple[tuple[str, int], ...]
    created_events_by_topic: tuple[tuple[str, int], ...]
    pending_events_by_producer_cohort: tuple[tuple[str, str, int], ...]
    created_events_by_producer_cohort: tuple[tuple[str, str, int], ...]


@dataclass(frozen=True, slots=True)
class DerivedStateResourceSample:
    """A time-aligned database and derived-state runtime observation."""

    captured_at: str
    database: DatabaseResourceUsage
    runtime: RuntimeResourceUsage
    outbox: OutboxResourceUsage


@dataclass(frozen=True, slots=True)
class DerivedStateResourceEvidence:
    """Peak resource evidence across one governed workload."""

    sample_count: int
    sampling_error_count: int
    sampling_error_types: tuple[str, ...]
    peak_database_total_connections: int | None
    peak_database_active_connections: int | None
    peak_database_idle_in_transaction_connections: int | None
    peak_database_lock_waiters: int | None
    peak_database_blocked_sessions: int | None
    peak_database_connection_utilization_percent: float | None
    peak_runtime_cpu_percent: float | None
    peak_runtime_memory_usage_bytes: int | None
    peak_runtime_memory_utilization_percent: float | None
    peak_outbox_pending_events: int | None
    peak_outbox_oldest_pending_age_seconds: float | None
    peak_outbox_recent_publication_age_p50_seconds: float | None
    peak_outbox_recent_publication_age_p95_seconds: float | None
    peak_outbox_recent_publication_age_p99_seconds: float | None
    peak_outbox_retry_eligible_pending_events: int | None
    peak_outbox_retry_waiting_pending_events: int | None
    peak_outbox_failed_events: int | None
    final_outbox_pending_events: int | None
    final_outbox_processed_events: int | None
    final_outbox_failed_events: int | None
    final_outbox_pending_events_by_topic: tuple[tuple[str, int], ...]
    final_outbox_created_events_by_topic: tuple[tuple[str, int], ...]
    final_outbox_pending_events_by_producer_cohort: tuple[tuple[str, str, int], ...]
    final_outbox_created_events_by_producer_cohort: tuple[tuple[str, str, int], ...]
    observed_outbox_processed_events: int | None
    observed_outbox_seconds: float | None
    observed_outbox_processed_events_per_second: float | None
    peak_database_usage_by_application: tuple[DatabaseApplicationResourceUsage, ...] = ()
    database_cohort_reconciled_sample_count: int = 0


def parse_memory_bytes(value: str) -> int:
    """Convert a Docker memory value with decimal or binary units to bytes."""

    match = _MEMORY_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"Unsupported Docker memory value: {value!r}")
    amount, unit = match.groups()
    return int(Decimal(amount) * _MEMORY_UNIT_MULTIPLIERS[unit.upper()])


def _parse_percent(value: object, *, field_name: str) -> float:
    raw = str(value).strip()
    if not raw.endswith("%"):
        raise ValueError(f"Docker stats field {field_name} is not a percentage: {raw!r}")
    return round(float(raw[:-1]), 4)


def _first_present(row: Mapping[str, Any], *field_names: str) -> object:
    for field_name in field_names:
        if field_name in row:
            return row[field_name]
    raise ValueError(f"Docker stats omitted required fields: {', '.join(field_names)}")


def _decode_compose_stats(payload: str) -> Mapping[str, Any]:
    stripped = payload.strip()
    if not stripped:
        raise ValueError("Docker Compose returned no resource statistics")
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        decoded = json.loads(stripped.splitlines()[0])
    if isinstance(decoded, list):
        if len(decoded) != 1:
            raise ValueError(f"Expected one derived-state stats row, received {len(decoded)}")
        decoded = decoded[0]
    if not isinstance(decoded, dict):
        raise ValueError("Docker Compose resource statistics must be a JSON object")
    return decoded


def parse_compose_stats(payload: str) -> RuntimeResourceUsage:
    """Parse one Docker Compose JSON stats observation across supported field names."""

    row = _decode_compose_stats(payload)
    memory_value = str(_first_present(row, "Memory", "MemUsage"))
    memory_parts = memory_value.split("/", maxsplit=1)
    if len(memory_parts) != 2:
        raise ValueError(f"Docker stats memory usage lacks a limit: {memory_value!r}")
    return RuntimeResourceUsage(
        cpu_percent=_parse_percent(
            _first_present(row, "CPU", "CPUPerc"),
            field_name="CPU",
        ),
        memory_usage_bytes=parse_memory_bytes(memory_parts[0]),
        memory_limit_bytes=parse_memory_bytes(memory_parts[1]),
        memory_utilization_percent=_parse_percent(
            _first_present(row, "MemoryPercentage", "MemPerc"),
            field_name="memory percentage",
        ),
    )


def _database_application_cohorts(
    value: object,
) -> tuple[DatabaseApplicationResourceUsage, ...]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, list):
        raise RuntimeError("Database resource query returned invalid application cohorts")
    cohorts = tuple(
        DatabaseApplicationResourceUsage(
            application_name=str(item["application_name"]),
            total_connections=int(item["total_connections"]),
            active_connections=int(item["active_connections"]),
            idle_in_transaction_connections=int(item["idle_in_transaction_connections"]),
            open_transactions=int(item["open_transactions"]),
            lock_waiters=int(item["lock_waiters"]),
            blocked_sessions=int(item["blocked_sessions"]),
            oldest_open_transaction_seconds=round(
                float(item["oldest_open_transaction_seconds"]), 6
            ),
            oldest_idle_in_transaction_seconds=round(
                float(item["oldest_idle_in_transaction_seconds"]), 6
            ),
        )
        for item in decoded
        if isinstance(item, dict)
    )
    if len(cohorts) != len(decoded):
        raise RuntimeError("Database resource query returned malformed application cohorts")
    allowed_cohorts = GOVERNED_DATABASE_APPLICATION_COHORTS | {
        _UNATTRIBUTED_APPLICATION,
        _UNGOVERNED_APPLICATION,
    }
    if any(cohort.application_name not in allowed_cohorts for cohort in cohorts):
        raise RuntimeError("Database resource query returned an unbounded application cohort")
    if not any(cohort.application_name == _UNATTRIBUTED_APPLICATION for cohort in cohorts):
        raise RuntimeError("Database resource query omitted the unattributed application cohort")
    return tuple(sorted(cohorts, key=lambda cohort: cohort.application_name))


def read_database_resource_usage(*, engine: Engine) -> DatabaseResourceUsage:
    """Read aggregate and bounded application-attributed pressure in one statement."""

    with engine.connect() as connection:
        row = (
            connection.execute(
                _DATABASE_RESOURCE_QUERY,
                {"governed_application_names": sorted(DATABASE_RUNTIME_IDENTITIES)},
            )
            .mappings()
            .one()
        )
    total_connections = int(row["total_connections"])
    active_connections = int(row["active_connections"])
    idle_in_transaction_connections = int(row["idle_in_transaction_connections"])
    application_cohorts = _database_application_cohorts(row["application_cohorts"])
    reconciled_counts = {
        "total_connections": total_connections,
        "active_connections": active_connections,
        "idle_in_transaction_connections": idle_in_transaction_connections,
    }
    for field_name, aggregate_count in reconciled_counts.items():
        cohort_count = sum(getattr(cohort, field_name) for cohort in application_cohorts)
        if cohort_count != aggregate_count:
            raise RuntimeError(
                "Database application-cohort reconciliation failed: "
                f"{field_name} {cohort_count} != aggregate {aggregate_count}"
            )
    max_connections = int(row["max_connections"])
    utilization = (
        round((total_connections / max_connections) * 100, 4) if max_connections > 0 else 0.0
    )
    return DatabaseResourceUsage(
        total_connections=total_connections,
        active_connections=active_connections,
        idle_in_transaction_connections=idle_in_transaction_connections,
        lock_waiters=int(row["lock_waiters"]),
        blocked_sessions=int(row["blocked_sessions"]),
        max_connections=max_connections,
        connection_utilization_percent=utilization,
        application_cohorts=application_cohorts,
    )


def _outbox_topic_totals(
    rows: Iterable[Mapping[str, Any]],
    *,
    count_field: str,
    omit_zero: bool = False,
) -> tuple[tuple[str, int], ...]:
    """Aggregate bounded producer cohorts into stable topic-level totals."""

    totals: dict[str, int] = {}
    for row in rows:
        topic = str(row["topic"])
        totals[topic] = totals.get(topic, 0) + int(row[count_field])
    return tuple(
        (topic, count) for topic, count in sorted(totals.items()) if not omit_zero or count > 0
    )


def read_outbox_resource_usage(*, engine: Engine) -> OutboxResourceUsage:
    """Read backlog, age, and cohorts from one consistent statement snapshot."""

    with engine.connect() as connection:
        rows = connection.execute(_OUTBOX_RESOURCE_QUERY).mappings().all()
    if not rows:
        raise RuntimeError("Outbox resource query returned no aggregate row")
    totals = rows[0]
    topic_rows = tuple(row for row in rows if row["topic"] is not None)
    return OutboxResourceUsage(
        pending_events=int(totals["pending_events"]),
        processed_events=int(totals["processed_events"]),
        failed_events=int(totals["failed_events"]),
        retry_eligible_pending_events=int(totals["retry_eligible_pending_events"]),
        retry_waiting_pending_events=int(totals["retry_waiting_pending_events"]),
        oldest_pending_age_seconds=round(float(totals["oldest_pending_age_seconds"]), 6),
        recent_publication_age_p50_seconds=round(
            float(totals["recent_publication_age_p50_seconds"]), 6
        ),
        recent_publication_age_p95_seconds=round(
            float(totals["recent_publication_age_p95_seconds"]), 6
        ),
        recent_publication_age_p99_seconds=round(
            float(totals["recent_publication_age_p99_seconds"]), 6
        ),
        pending_events_by_topic=_outbox_topic_totals(
            topic_rows,
            count_field="cohort_pending_events",
            omit_zero=True,
        ),
        created_events_by_topic=_outbox_topic_totals(
            topic_rows,
            count_field="cohort_created_events",
        ),
        pending_events_by_producer_cohort=tuple(
            sorted(
                (
                    str(row["aggregate_type"]),
                    str(row["topic"]),
                    int(row["cohort_pending_events"]),
                )
                for row in topic_rows
                if int(row["cohort_pending_events"]) > 0
            )
        ),
        created_events_by_producer_cohort=tuple(
            sorted(
                (
                    str(row["aggregate_type"]),
                    str(row["topic"]),
                    int(row["cohort_created_events"]),
                )
                for row in topic_rows
            )
        ),
    )


def read_runtime_resource_usage(
    *,
    repo_root: Path,
    compose_file: str,
    compose_project_name: str,
    service_name: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> RuntimeResourceUsage:
    """Read one no-stream resource observation for the exact Compose service."""

    completed = runner(
        [
            "docker",
            "compose",
            "-f",
            compose_file,
            "-p",
            compose_project_name,
            "stats",
            "--no-stream",
            "--format",
            "json",
            service_name,
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_compose_stats(completed.stdout)


def capture_resource_sample(
    *,
    engine: Engine,
    repo_root: Path,
    compose_file: str,
    compose_project_name: str,
    service_name: str,
) -> DerivedStateResourceSample:
    """Capture one database and container observation for the workload report."""

    return DerivedStateResourceSample(
        captured_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        database=read_database_resource_usage(engine=engine),
        runtime=read_runtime_resource_usage(
            repo_root=repo_root,
            compose_file=compose_file,
            compose_project_name=compose_project_name,
            service_name=service_name,
        ),
        outbox=read_outbox_resource_usage(engine=engine),
    )


def _maximum(
    samples: tuple[DerivedStateResourceSample, ...],
    reader: Callable[[DerivedStateResourceSample], _ResourceValue],
) -> _ResourceValue | None:
    return max((reader(sample) for sample in samples), default=None)


def _outbox_throughput(
    samples: tuple[DerivedStateResourceSample, ...],
) -> tuple[int | None, float | None, float | None]:
    """Calculate observed processed-event throughput across a real sampling window."""

    if len(samples) < 2:
        return None, None, None
    started_at = datetime.fromisoformat(samples[0].captured_at.replace("Z", "+00:00"))
    ended_at = datetime.fromisoformat(samples[-1].captured_at.replace("Z", "+00:00"))
    elapsed_seconds = max((ended_at - started_at).total_seconds(), 0.0)
    processed_events = max(
        samples[-1].outbox.processed_events - samples[0].outbox.processed_events,
        0,
    )
    if elapsed_seconds == 0:
        return processed_events, 0.0, None
    return (
        processed_events,
        round(elapsed_seconds, 6),
        round(processed_events / elapsed_seconds, 6),
    )


def _maximum_database_application_usage(
    cohorts: Iterable[DatabaseApplicationResourceUsage],
    *,
    application_name: str,
) -> DatabaseApplicationResourceUsage:
    values = tuple(cohorts)
    return DatabaseApplicationResourceUsage(
        application_name=application_name,
        total_connections=max((value.total_connections for value in values), default=0),
        active_connections=max((value.active_connections for value in values), default=0),
        idle_in_transaction_connections=max(
            (value.idle_in_transaction_connections for value in values), default=0
        ),
        open_transactions=max((value.open_transactions for value in values), default=0),
        lock_waiters=max((value.lock_waiters for value in values), default=0),
        blocked_sessions=max((value.blocked_sessions for value in values), default=0),
        oldest_open_transaction_seconds=max(
            (value.oldest_open_transaction_seconds for value in values), default=0.0
        ),
        oldest_idle_in_transaction_seconds=max(
            (value.oldest_idle_in_transaction_seconds for value in values), default=0.0
        ),
    )


def _bounded_peak_database_application_usage(
    cohort_values: Iterable[DatabaseApplicationResourceUsage],
) -> tuple[DatabaseApplicationResourceUsage, ...]:
    """Retain deterministic peaks without allowing application cardinality to grow unbounded."""

    cohorts = tuple(cohort_values)
    allowed_cohorts = GOVERNED_DATABASE_APPLICATION_COHORTS | {
        _UNATTRIBUTED_APPLICATION,
        _UNGOVERNED_APPLICATION,
    }
    if any(cohort.application_name not in allowed_cohorts for cohort in cohorts):
        raise RuntimeError("Database samples contain an unbounded application cohort")
    observations: dict[str, list[DatabaseApplicationResourceUsage]] = {}
    for cohort in cohorts:
        observations.setdefault(cohort.application_name, []).append(cohort)
    peaks = {
        application_name: _maximum_database_application_usage(
            values, application_name=application_name
        )
        for application_name, values in observations.items()
    }
    return tuple(sorted(peaks.values(), key=lambda cohort: cohort.application_name))


def _peak_database_application_usage(
    samples: tuple[DerivedStateResourceSample, ...],
) -> tuple[DatabaseApplicationResourceUsage, ...]:
    return _bounded_peak_database_application_usage(
        cohort for sample in samples for cohort in sample.database.application_cohorts
    )


def _database_cohorts_reconcile(database: DatabaseResourceUsage) -> bool:
    cohorts = database.application_cohorts
    return bool(cohorts) and all(
        sum(getattr(cohort, field_name) for cohort in cohorts) == aggregate_count
        for field_name, aggregate_count in (
            ("total_connections", database.total_connections),
            ("active_connections", database.active_connections),
            (
                "idle_in_transaction_connections",
                database.idle_in_transaction_connections,
            ),
        )
    )


def summarize_resource_samples(
    *,
    samples: Iterable[DerivedStateResourceSample],
    sampling_errors: Iterable[str],
) -> DerivedStateResourceEvidence:
    """Reduce time-series samples into bounded machine-readable peak evidence."""

    sample_values = tuple(samples)
    error_values = tuple(sampling_errors)
    final_outbox = sample_values[-1].outbox if sample_values else None
    processed_events, observed_seconds, processed_per_second = _outbox_throughput(sample_values)
    return DerivedStateResourceEvidence(
        sample_count=len(sample_values),
        sampling_error_count=len(error_values),
        sampling_error_types=tuple(sorted(set(error_values))),
        peak_database_total_connections=_maximum(
            sample_values, lambda sample: sample.database.total_connections
        ),
        peak_database_active_connections=_maximum(
            sample_values, lambda sample: sample.database.active_connections
        ),
        peak_database_idle_in_transaction_connections=_maximum(
            sample_values,
            lambda sample: sample.database.idle_in_transaction_connections,
        ),
        peak_database_lock_waiters=_maximum(
            sample_values, lambda sample: sample.database.lock_waiters
        ),
        peak_database_blocked_sessions=_maximum(
            sample_values, lambda sample: sample.database.blocked_sessions
        ),
        peak_database_connection_utilization_percent=_maximum(
            sample_values,
            lambda sample: sample.database.connection_utilization_percent,
        ),
        peak_runtime_cpu_percent=_maximum(sample_values, lambda sample: sample.runtime.cpu_percent),
        peak_runtime_memory_usage_bytes=_maximum(
            sample_values, lambda sample: sample.runtime.memory_usage_bytes
        ),
        peak_runtime_memory_utilization_percent=_maximum(
            sample_values, lambda sample: sample.runtime.memory_utilization_percent
        ),
        peak_outbox_pending_events=_maximum(
            sample_values, lambda sample: sample.outbox.pending_events
        ),
        peak_outbox_oldest_pending_age_seconds=_maximum(
            sample_values, lambda sample: sample.outbox.oldest_pending_age_seconds
        ),
        peak_outbox_recent_publication_age_p50_seconds=_maximum(
            sample_values, lambda sample: sample.outbox.recent_publication_age_p50_seconds
        ),
        peak_outbox_recent_publication_age_p95_seconds=_maximum(
            sample_values, lambda sample: sample.outbox.recent_publication_age_p95_seconds
        ),
        peak_outbox_recent_publication_age_p99_seconds=_maximum(
            sample_values, lambda sample: sample.outbox.recent_publication_age_p99_seconds
        ),
        peak_outbox_retry_eligible_pending_events=_maximum(
            sample_values,
            lambda sample: sample.outbox.retry_eligible_pending_events,
        ),
        peak_outbox_retry_waiting_pending_events=_maximum(
            sample_values,
            lambda sample: sample.outbox.retry_waiting_pending_events,
        ),
        peak_outbox_failed_events=_maximum(
            sample_values, lambda sample: sample.outbox.failed_events
        ),
        final_outbox_pending_events=(final_outbox.pending_events if final_outbox else None),
        final_outbox_processed_events=(final_outbox.processed_events if final_outbox else None),
        final_outbox_failed_events=(final_outbox.failed_events if final_outbox else None),
        final_outbox_pending_events_by_topic=(
            final_outbox.pending_events_by_topic if final_outbox else ()
        ),
        final_outbox_created_events_by_topic=(
            final_outbox.created_events_by_topic if final_outbox else ()
        ),
        final_outbox_pending_events_by_producer_cohort=(
            final_outbox.pending_events_by_producer_cohort if final_outbox else ()
        ),
        final_outbox_created_events_by_producer_cohort=(
            final_outbox.created_events_by_producer_cohort if final_outbox else ()
        ),
        observed_outbox_processed_events=processed_events,
        observed_outbox_seconds=observed_seconds,
        observed_outbox_processed_events_per_second=processed_per_second,
        peak_database_usage_by_application=_peak_database_application_usage(sample_values),
        database_cohort_reconciled_sample_count=sum(
            _database_cohorts_reconcile(sample.database) for sample in sample_values
        ),
    )


class DerivedStateResourceMonitor:
    """Supervise periodic resource sampling without interrupting the workload thread."""

    def __init__(
        self,
        *,
        sample_reader: Callable[[], DerivedStateResourceSample],
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._sample_reader = sample_reader
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._samples: list[DerivedStateResourceSample] = []
        self._sampling_errors: list[str] = []

    @property
    def samples(self) -> tuple[DerivedStateResourceSample, ...]:
        """Return completed observations in capture order."""

        return tuple(self._samples)

    def start(self) -> None:
        """Start supervised sampling."""

        self._thread.start()

    def stop(self) -> None:
        """Stop sampling and append one final observation after the worker exits."""

        self._stop_event.set()
        self._thread.join(timeout=max(self._interval_seconds * 2, 5))
        try:
            self._samples.append(self._sample_reader())
        except Exception as exc:
            self._sampling_errors.append(type(exc).__name__)

    def evidence(self) -> DerivedStateResourceEvidence:
        """Return peak evidence and bounded sampling diagnostics."""

        return summarize_resource_samples(
            samples=self._samples,
            sampling_errors=self._sampling_errors,
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._samples.append(self._sample_reader())
            except Exception as exc:  # Sampling failure must not terminate the workload.
                self._sampling_errors.append(type(exc).__name__)
            self._stop_event.wait(self._interval_seconds)
