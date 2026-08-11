"""Tests for derived-state database and runtime resource evidence."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from portfolio_common.database_runtime_identity import DATABASE_RUNTIME_IDENTITIES

from scripts.operations.performance.derived_state_resource_monitor import (
    DatabaseApplicationResourceUsage,
    DatabaseResourceUsage,
    DerivedStateResourceSample,
    OutboxResourceUsage,
    RuntimeResourceUsage,
    _bounded_peak_database_application_usage,
    parse_compose_stats,
    parse_memory_bytes,
    read_database_resource_usage,
    read_outbox_resource_usage,
    read_runtime_resource_usage,
    summarize_resource_samples,
)


def test_parse_memory_bytes_supports_compose_binary_units() -> None:
    assert parse_memory_bytes("512KiB") == 512 * 1024
    assert parse_memory_bytes("128.5MiB") == int(128.5 * 1024**2)
    assert parse_memory_bytes("1.25GiB") == int(1.25 * 1024**3)


def test_parse_compose_stats_preserves_cpu_memory_and_capacity() -> None:
    usage = parse_compose_stats(
        '{"Name":"derived-state","CPU":"12.50%",'
        '"Memory":"128.5MiB / 2GiB","MemoryPercentage":"6.27%"}'
    )

    assert usage == RuntimeResourceUsage(
        cpu_percent=12.5,
        memory_usage_bytes=int(128.5 * 1024**2),
        memory_limit_bytes=2 * 1024**3,
        memory_utilization_percent=6.27,
    )


def test_parse_compose_stats_accepts_array_and_docker_field_names() -> None:
    usage = parse_compose_stats(
        '[{"Name":"derived-state","CPUPerc":"0.75%","MemUsage":"64MiB / 1GiB","MemPerc":"6.25%"}]'
    )

    assert usage.cpu_percent == 0.75
    assert usage.memory_usage_bytes == 64 * 1024**2
    assert usage.memory_limit_bytes == 1024**3
    assert usage.memory_utilization_percent == 6.25


def test_read_database_resource_usage_calculates_connection_capacity() -> None:
    captured: dict[str, object] = {}

    class Result:
        def mappings(self) -> Result:
            return self

        def one(self) -> dict[str, object]:
            return {
                "total_connections": 25,
                "active_connections": 12,
                "idle_in_transaction_connections": 2,
                "lock_waiters": 3,
                "blocked_sessions": 1,
                "max_connections": 200,
                "application_cohorts": [
                    {
                        "application_name": "__unattributed__",
                        "total_connections": 5,
                        "active_connections": 2,
                        "idle_in_transaction_connections": 1,
                        "open_transactions": 1,
                        "lock_waiters": 0,
                        "blocked_sessions": 0,
                        "oldest_open_transaction_seconds": 8.1234567,
                        "oldest_idle_in_transaction_seconds": 8.1234567,
                    },
                    {
                        "application_name": "portfolio-derived-state",
                        "total_connections": 20,
                        "active_connections": 10,
                        "idle_in_transaction_connections": 1,
                        "open_transactions": 4,
                        "lock_waiters": 3,
                        "blocked_sessions": 1,
                        "oldest_open_transaction_seconds": 12.5,
                        "oldest_idle_in_transaction_seconds": 4.0,
                    },
                ],
            }

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: object, params: dict[str, object]) -> Result:
            captured["query"] = str(query)
            captured["params"] = params
            return Result()

    class Engine:
        def connect(self) -> Connection:
            return Connection()

    usage = read_database_resource_usage(engine=Engine())  # type: ignore[arg-type]

    assert usage.total_connections == 25
    assert usage.active_connections == 12
    assert usage.lock_waiters == 3
    assert usage.blocked_sessions == 1
    assert usage.connection_utilization_percent == 12.5
    assert usage.application_cohorts[0].application_name == "__unattributed__"
    assert usage.application_cohorts[1].open_transactions == 4
    assert usage.application_cohorts[1].oldest_open_transaction_seconds == 12.5
    assert captured["params"] == {"governed_application_names": sorted(DATABASE_RUNTIME_IDENTITIES)}
    assert "FROM pg_stat_activity" in str(captured["query"])
    assert "jsonb_agg" in str(captured["query"])
    assert "NOT waiting_lock.granted" in str(captured["query"])


def test_read_database_resource_usage_rejects_unreconciled_cohorts() -> None:
    class Result:
        def mappings(self) -> Result:
            return self

        def one(self) -> dict[str, object]:
            return {
                "total_connections": 2,
                "active_connections": 1,
                "idle_in_transaction_connections": 0,
                "lock_waiters": 0,
                "blocked_sessions": 0,
                "max_connections": 100,
                "application_cohorts": [
                    {
                        "application_name": "__unattributed__",
                        "total_connections": 1,
                        "active_connections": 1,
                        "idle_in_transaction_connections": 0,
                        "open_transactions": 1,
                        "lock_waiters": 0,
                        "blocked_sessions": 0,
                        "oldest_open_transaction_seconds": 0,
                        "oldest_idle_in_transaction_seconds": 0,
                    }
                ],
            }

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _query: object, _params: object) -> Result:
            return Result()

    class Engine:
        def connect(self) -> Connection:
            return Connection()

    with pytest.raises(RuntimeError, match="total_connections 1 != aggregate 2"):
        read_database_resource_usage(engine=Engine())  # type: ignore[arg-type]


def test_database_application_peak_summary_is_bounded_to_governed_inventory() -> None:
    cohorts = tuple(
        DatabaseApplicationResourceUsage(
            application_name=application_name,
            total_connections=1,
            active_connections=1,
            idle_in_transaction_connections=0,
            open_transactions=1,
            lock_waiters=0,
            blocked_sessions=0,
            oldest_open_transaction_seconds=float(index),
            oldest_idle_in_transaction_seconds=0.0,
        )
        for index, application_name in enumerate(sorted(DATABASE_RUNTIME_IDENTITIES))
    ) + (
        DatabaseApplicationResourceUsage(
            application_name="__unattributed__",
            total_connections=0,
            active_connections=0,
            idle_in_transaction_connections=0,
            open_transactions=0,
            lock_waiters=0,
            blocked_sessions=0,
            oldest_open_transaction_seconds=0.0,
            oldest_idle_in_transaction_seconds=0.0,
        ),
    )

    peaks = _bounded_peak_database_application_usage(cohorts)

    assert len(peaks) == len(DATABASE_RUNTIME_IDENTITIES) + 1
    assert DATABASE_RUNTIME_IDENTITIES <= {peak.application_name for peak in peaks}
    assert "__unattributed__" in {peak.application_name for peak in peaks}


def test_database_application_peak_summary_rejects_free_form_identity() -> None:
    cohort = DatabaseApplicationResourceUsage(
        application_name="portfolio-PB_SG_GLOBAL_BAL_001",
        total_connections=1,
        active_connections=1,
        idle_in_transaction_connections=0,
        open_transactions=1,
        lock_waiters=0,
        blocked_sessions=0,
        oldest_open_transaction_seconds=0.0,
        oldest_idle_in_transaction_seconds=0.0,
    )

    with pytest.raises(RuntimeError, match="unbounded application cohort"):
        _bounded_peak_database_application_usage((cohort,))


def test_read_runtime_resource_usage_targets_exact_compose_service() -> None:
    captured: dict[str, object] = {}

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=('{"CPU":"1.50%","Memory":"32MiB / 1GiB","MemoryPercentage":"3.125%"}'),
            stderr="",
        )

    usage = read_runtime_resource_usage(
        repo_root=Path("C:/lotus-core"),
        compose_file="docker-compose.e2e.yml",
        compose_project_name="derived-state-proof",
        service_name="portfolio_derived_state_service",
        runner=runner,
    )

    assert captured["command"] == [
        "docker",
        "compose",
        "-f",
        "docker-compose.e2e.yml",
        "-p",
        "derived-state-proof",
        "stats",
        "--no-stream",
        "--format",
        "json",
        "portfolio_derived_state_service",
    ]
    assert captured["kwargs"] == {
        "cwd": Path("C:/lotus-core"),
        "check": True,
        "capture_output": True,
        "text": True,
    }
    assert usage.memory_usage_bytes == 32 * 1024**2


def test_read_outbox_resource_usage_preserves_backlog_and_topic_cohorts() -> None:
    class Result:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self._rows = rows

        def mappings(self) -> Result:
            return self

        def one(self) -> dict[str, object]:
            return self._rows[0]

        def all(self) -> list[dict[str, object]]:
            return self._rows

    class Connection:
        def __init__(self) -> None:
            self._call_count = 0

        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _query: object) -> Result:
            self._call_count += 1
            assert self._call_count == 1
            return Result(
                [
                    {
                        "pending_events": 120,
                        "processed_events": 880,
                        "failed_events": 2,
                        "retry_eligible_pending_events": 115,
                        "retry_waiting_pending_events": 5,
                        "oldest_pending_age_seconds": 42.1256789,
                        "recent_publication_age_p50_seconds": 2.25,
                        "recent_publication_age_p95_seconds": 8.5,
                        "recent_publication_age_p99_seconds": 12.75,
                        "aggregate_type": "RawTransaction",
                        "topic": "transactions.persisted",
                        "cohort_created_events": 700,
                        "cohort_pending_events": 100,
                    },
                    {
                        "pending_events": 120,
                        "processed_events": 880,
                        "failed_events": 2,
                        "retry_eligible_pending_events": 115,
                        "retry_waiting_pending_events": 5,
                        "oldest_pending_age_seconds": 42.1256789,
                        "recent_publication_age_p50_seconds": 2.25,
                        "recent_publication_age_p95_seconds": 8.5,
                        "recent_publication_age_p99_seconds": 12.75,
                        "aggregate_type": "DailyPositionSnapshot",
                        "topic": "valuation.snapshot.persisted",
                        "cohort_created_events": 300,
                        "cohort_pending_events": 0,
                    },
                    {
                        "pending_events": 120,
                        "processed_events": 880,
                        "failed_events": 2,
                        "retry_eligible_pending_events": 115,
                        "retry_waiting_pending_events": 5,
                        "oldest_pending_age_seconds": 42.1256789,
                        "recent_publication_age_p50_seconds": 2.25,
                        "recent_publication_age_p95_seconds": 8.5,
                        "recent_publication_age_p99_seconds": 12.75,
                        "aggregate_type": "TransactionReplay",
                        "topic": "transactions.persisted",
                        "cohort_created_events": 50,
                        "cohort_pending_events": 5,
                    },
                ]
            )

    class Engine:
        def connect(self) -> Connection:
            return Connection()

    usage = read_outbox_resource_usage(engine=Engine())  # type: ignore[arg-type]

    assert usage.pending_events == 120
    assert usage.processed_events == 880
    assert usage.failed_events == 2
    assert usage.retry_eligible_pending_events == 115
    assert usage.retry_waiting_pending_events == 5
    assert usage.oldest_pending_age_seconds == 42.125679
    assert usage.recent_publication_age_p50_seconds == 2.25
    assert usage.recent_publication_age_p95_seconds == 8.5
    assert usage.recent_publication_age_p99_seconds == 12.75
    assert usage.pending_events_by_topic == (("transactions.persisted", 105),)
    assert usage.created_events_by_topic == (
        ("transactions.persisted", 750),
        ("valuation.snapshot.persisted", 300),
    )
    assert usage.pending_events_by_producer_cohort == (
        ("RawTransaction", "transactions.persisted", 100),
        ("TransactionReplay", "transactions.persisted", 5),
    )
    assert usage.created_events_by_producer_cohort == (
        ("DailyPositionSnapshot", "valuation.snapshot.persisted", 300),
        ("RawTransaction", "transactions.persisted", 700),
        ("TransactionReplay", "transactions.persisted", 50),
    )


def test_read_outbox_resource_usage_preserves_totals_when_no_cohorts_exist() -> None:
    class Result:
        def mappings(self) -> Result:
            return self

        def all(self) -> list[dict[str, object]]:
            return [
                {
                    "pending_events": 0,
                    "processed_events": 0,
                    "failed_events": 0,
                    "retry_eligible_pending_events": 0,
                    "retry_waiting_pending_events": 0,
                    "oldest_pending_age_seconds": 0,
                    "recent_publication_age_p50_seconds": 0,
                    "recent_publication_age_p95_seconds": 0,
                    "recent_publication_age_p99_seconds": 0,
                    "aggregate_type": None,
                    "topic": None,
                    "cohort_created_events": None,
                    "cohort_pending_events": None,
                }
            ]

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _query: object) -> Result:
            return Result()

    class Engine:
        def connect(self) -> Connection:
            return Connection()

    usage = read_outbox_resource_usage(engine=Engine())  # type: ignore[arg-type]

    assert usage.pending_events == 0
    assert usage.created_events_by_topic == ()
    assert usage.pending_events_by_producer_cohort == ()


def test_summarize_resource_samples_reports_peak_capacity_pressure() -> None:
    samples = (
        DerivedStateResourceSample(
            captured_at="2026-07-15T09:00:00Z",
            database=DatabaseResourceUsage(
                total_connections=8,
                active_connections=3,
                idle_in_transaction_connections=1,
                lock_waiters=0,
                blocked_sessions=0,
                max_connections=100,
                connection_utilization_percent=8.0,
                application_cohorts=(
                    DatabaseApplicationResourceUsage(
                        application_name="__unattributed__",
                        total_connections=2,
                        active_connections=1,
                        idle_in_transaction_connections=1,
                        open_transactions=1,
                        lock_waiters=0,
                        blocked_sessions=0,
                        oldest_open_transaction_seconds=2.0,
                        oldest_idle_in_transaction_seconds=2.0,
                    ),
                    DatabaseApplicationResourceUsage(
                        application_name="portfolio-derived-state",
                        total_connections=6,
                        active_connections=2,
                        idle_in_transaction_connections=0,
                        open_transactions=1,
                        lock_waiters=0,
                        blocked_sessions=0,
                        oldest_open_transaction_seconds=1.0,
                        oldest_idle_in_transaction_seconds=0.0,
                    ),
                ),
            ),
            runtime=RuntimeResourceUsage(
                cpu_percent=20.0,
                memory_usage_bytes=128 * 1024**2,
                memory_limit_bytes=1024**3,
                memory_utilization_percent=12.5,
            ),
            outbox=OutboxResourceUsage(
                pending_events=100,
                processed_events=300,
                failed_events=0,
                retry_eligible_pending_events=90,
                retry_waiting_pending_events=10,
                oldest_pending_age_seconds=15.0,
                recent_publication_age_p50_seconds=1.0,
                recent_publication_age_p95_seconds=4.0,
                recent_publication_age_p99_seconds=7.0,
                pending_events_by_topic=(("transactions.persisted", 100),),
                created_events_by_topic=(("transactions.persisted", 400),),
                pending_events_by_producer_cohort=(
                    ("RawTransaction", "transactions.persisted", 100),
                ),
                created_events_by_producer_cohort=(
                    ("RawTransaction", "transactions.persisted", 400),
                ),
            ),
        ),
        DerivedStateResourceSample(
            captured_at="2026-07-15T09:00:05Z",
            database=DatabaseResourceUsage(
                total_connections=15,
                active_connections=9,
                idle_in_transaction_connections=2,
                lock_waiters=4,
                blocked_sessions=2,
                max_connections=100,
                connection_utilization_percent=15.0,
                application_cohorts=(
                    DatabaseApplicationResourceUsage(
                        application_name="__unattributed__",
                        total_connections=3,
                        active_connections=1,
                        idle_in_transaction_connections=1,
                        open_transactions=1,
                        lock_waiters=0,
                        blocked_sessions=0,
                        oldest_open_transaction_seconds=7.0,
                        oldest_idle_in_transaction_seconds=7.0,
                    ),
                    DatabaseApplicationResourceUsage(
                        application_name="portfolio-derived-state",
                        total_connections=12,
                        active_connections=8,
                        idle_in_transaction_connections=1,
                        open_transactions=3,
                        lock_waiters=4,
                        blocked_sessions=2,
                        oldest_open_transaction_seconds=6.0,
                        oldest_idle_in_transaction_seconds=5.0,
                    ),
                ),
            ),
            runtime=RuntimeResourceUsage(
                cpu_percent=72.5,
                memory_usage_bytes=320 * 1024**2,
                memory_limit_bytes=1024**3,
                memory_utilization_percent=31.25,
            ),
            outbox=OutboxResourceUsage(
                pending_events=250,
                processed_events=750,
                failed_events=1,
                retry_eligible_pending_events=240,
                retry_waiting_pending_events=10,
                oldest_pending_age_seconds=45.0,
                recent_publication_age_p50_seconds=2.0,
                recent_publication_age_p95_seconds=6.0,
                recent_publication_age_p99_seconds=9.0,
                pending_events_by_topic=(
                    ("transactions.persisted", 200),
                    ("valuation.snapshot.persisted", 50),
                ),
                created_events_by_topic=(
                    ("transactions.persisted", 700),
                    ("valuation.snapshot.persisted", 300),
                ),
                pending_events_by_producer_cohort=(
                    ("RawTransaction", "transactions.persisted", 200),
                    ("DailyPositionSnapshot", "valuation.snapshot.persisted", 50),
                ),
                created_events_by_producer_cohort=(
                    ("RawTransaction", "transactions.persisted", 700),
                    ("DailyPositionSnapshot", "valuation.snapshot.persisted", 300),
                ),
            ),
        ),
    )

    evidence = summarize_resource_samples(samples=samples, sampling_errors=("RuntimeError",))

    assert evidence.sample_count == 2
    assert evidence.sampling_error_count == 1
    assert evidence.sampling_error_types == ("RuntimeError",)
    assert evidence.peak_database_total_connections == 15
    assert evidence.peak_database_active_connections == 9
    assert evidence.peak_database_idle_in_transaction_connections == 2
    assert evidence.peak_database_lock_waiters == 4
    assert evidence.peak_database_blocked_sessions == 2
    assert evidence.peak_database_connection_utilization_percent == 15.0
    assert evidence.database_cohort_reconciled_sample_count == 2
    assert evidence.peak_database_usage_by_application == (
        DatabaseApplicationResourceUsage(
            application_name="__unattributed__",
            total_connections=3,
            active_connections=1,
            idle_in_transaction_connections=1,
            open_transactions=1,
            lock_waiters=0,
            blocked_sessions=0,
            oldest_open_transaction_seconds=7.0,
            oldest_idle_in_transaction_seconds=7.0,
        ),
        DatabaseApplicationResourceUsage(
            application_name="portfolio-derived-state",
            total_connections=12,
            active_connections=8,
            idle_in_transaction_connections=1,
            open_transactions=3,
            lock_waiters=4,
            blocked_sessions=2,
            oldest_open_transaction_seconds=6.0,
            oldest_idle_in_transaction_seconds=5.0,
        ),
    )
    assert evidence.peak_runtime_cpu_percent == 72.5
    assert evidence.peak_runtime_memory_usage_bytes == 320 * 1024**2
    assert evidence.peak_runtime_memory_utilization_percent == 31.25
    assert evidence.peak_outbox_pending_events == 250
    assert evidence.peak_outbox_oldest_pending_age_seconds == 45.0
    assert evidence.peak_outbox_recent_publication_age_p50_seconds == 2.0
    assert evidence.peak_outbox_recent_publication_age_p95_seconds == 6.0
    assert evidence.peak_outbox_recent_publication_age_p99_seconds == 9.0
    assert evidence.peak_outbox_retry_eligible_pending_events == 240
    assert evidence.peak_outbox_retry_waiting_pending_events == 10
    assert evidence.peak_outbox_failed_events == 1
    assert evidence.final_outbox_pending_events == 250
    assert evidence.final_outbox_processed_events == 750
    assert evidence.final_outbox_failed_events == 1
    assert evidence.final_outbox_pending_events_by_topic == (
        ("transactions.persisted", 200),
        ("valuation.snapshot.persisted", 50),
    )
    assert evidence.final_outbox_created_events_by_topic == (
        ("transactions.persisted", 700),
        ("valuation.snapshot.persisted", 300),
    )
    assert evidence.final_outbox_pending_events_by_producer_cohort == (
        ("RawTransaction", "transactions.persisted", 200),
        ("DailyPositionSnapshot", "valuation.snapshot.persisted", 50),
    )
    assert evidence.final_outbox_created_events_by_producer_cohort == (
        ("RawTransaction", "transactions.persisted", 700),
        ("DailyPositionSnapshot", "valuation.snapshot.persisted", 300),
    )
    assert evidence.observed_outbox_processed_events == 450
    assert evidence.observed_outbox_seconds == 5.0
    assert evidence.observed_outbox_processed_events_per_second == 90.0


def test_summarize_resource_samples_is_explicit_when_no_sample_completed() -> None:
    evidence = summarize_resource_samples(samples=(), sampling_errors=("TimeoutError",))

    assert evidence.sample_count == 0
    assert evidence.sampling_error_count == 1
    assert evidence.peak_database_total_connections is None
    assert evidence.peak_runtime_memory_usage_bytes is None
    assert evidence.peak_outbox_pending_events is None
    assert evidence.peak_outbox_recent_publication_age_p99_seconds is None
    assert evidence.final_outbox_pending_events is None
    assert evidence.final_outbox_pending_events_by_topic == ()
    assert evidence.final_outbox_pending_events_by_producer_cohort == ()
    assert evidence.observed_outbox_processed_events is None
    assert evidence.observed_outbox_seconds is None
    assert evidence.observed_outbox_processed_events_per_second is None
