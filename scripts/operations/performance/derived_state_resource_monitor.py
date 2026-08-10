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

from sqlalchemy import Engine, text

_DATABASE_RESOURCE_QUERY = text(
    """
    SELECT
      count(*) FILTER (WHERE datname = current_database()) AS total_connections,
      count(*) FILTER (
        WHERE datname = current_database() AND state = 'active'
      ) AS active_connections,
      count(*) FILTER (
        WHERE datname = current_database() AND state = 'idle in transaction'
      ) AS idle_in_transaction_connections,
      (
        SELECT count(*)
        FROM pg_locks waiting_lock
        JOIN pg_stat_activity waiting_activity
          ON waiting_activity.pid = waiting_lock.pid
        WHERE waiting_activity.datname = current_database()
          AND NOT waiting_lock.granted
      ) AS lock_waiters,
      count(*) FILTER (
        WHERE datname = current_database()
          AND cardinality(pg_blocking_pids(pid)) > 0
      ) AS blocked_sessions,
      current_setting('max_connections')::integer AS max_connections
    FROM pg_stat_activity
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
class DatabaseResourceUsage:
    """One PostgreSQL capacity and lock-pressure observation."""

    total_connections: int
    active_connections: int
    idle_in_transaction_connections: int
    lock_waiters: int
    blocked_sessions: int
    max_connections: int
    connection_utilization_percent: float


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


def read_database_resource_usage(*, engine: Engine) -> DatabaseResourceUsage:
    """Read current database connections, blocked work, and lock waiters."""

    with engine.connect() as connection:
        row = connection.execute(_DATABASE_RESOURCE_QUERY).mappings().one()
    total_connections = int(row["total_connections"])
    max_connections = int(row["max_connections"])
    utilization = (
        round((total_connections / max_connections) * 100, 4) if max_connections > 0 else 0.0
    )
    return DatabaseResourceUsage(
        total_connections=total_connections,
        active_connections=int(row["active_connections"]),
        idle_in_transaction_connections=int(row["idle_in_transaction_connections"]),
        lock_waiters=int(row["lock_waiters"]),
        blocked_sessions=int(row["blocked_sessions"]),
        max_connections=max_connections,
        connection_utilization_percent=utilization,
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
