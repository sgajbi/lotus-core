"""Tests for derived-state database and runtime resource evidence."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.operations.performance.derived_state_resource_monitor import (
    DatabaseResourceUsage,
    DerivedStateResourceSample,
    OutboxResourceUsage,
    RuntimeResourceUsage,
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
    captured: dict[str, str] = {}

    class Result:
        def mappings(self) -> Result:
            return self

        def one(self) -> dict[str, int]:
            return {
                "total_connections": 25,
                "active_connections": 12,
                "idle_in_transaction_connections": 2,
                "lock_waiters": 3,
                "blocked_sessions": 1,
                "max_connections": 200,
            }

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: object) -> Result:
            captured["query"] = str(query)
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
    assert "JOIN pg_stat_activity waiting_activity" in captured["query"]
    assert "waiting_activity.datname = current_database()" in captured["query"]
    assert "NOT waiting_lock.granted" in captured["query"]


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
            if self._call_count == 1:
                return Result(
                    [
                        {
                            "pending_events": 120,
                            "processed_events": 880,
                            "failed_events": 2,
                            "retry_eligible_pending_events": 115,
                            "retry_waiting_pending_events": 5,
                            "oldest_pending_age_seconds": 42.1256789,
                        }
                    ]
                )
            return Result(
                [
                    {
                        "topic": "transactions.persisted",
                        "created_events": 700,
                        "pending_events": 100,
                    },
                    {
                        "topic": "valuation.snapshot.persisted",
                        "created_events": 300,
                        "pending_events": 0,
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
    assert usage.pending_events_by_topic == (("transactions.persisted", 100),)
    assert usage.created_events_by_topic == (
        ("transactions.persisted", 700),
        ("valuation.snapshot.persisted", 300),
    )


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
                pending_events_by_topic=(("transactions.persisted", 100),),
                created_events_by_topic=(("transactions.persisted", 400),),
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
                pending_events_by_topic=(
                    ("transactions.persisted", 200),
                    ("valuation.snapshot.persisted", 50),
                ),
                created_events_by_topic=(
                    ("transactions.persisted", 700),
                    ("valuation.snapshot.persisted", 300),
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
    assert evidence.peak_runtime_cpu_percent == 72.5
    assert evidence.peak_runtime_memory_usage_bytes == 320 * 1024**2
    assert evidence.peak_runtime_memory_utilization_percent == 31.25
    assert evidence.peak_outbox_pending_events == 250
    assert evidence.peak_outbox_oldest_pending_age_seconds == 45.0
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


def test_summarize_resource_samples_is_explicit_when_no_sample_completed() -> None:
    evidence = summarize_resource_samples(samples=(), sampling_errors=("TimeoutError",))

    assert evidence.sample_count == 0
    assert evidence.sampling_error_count == 1
    assert evidence.peak_database_total_connections is None
    assert evidence.peak_runtime_memory_usage_bytes is None
    assert evidence.peak_outbox_pending_events is None
    assert evidence.final_outbox_pending_events is None
    assert evidence.final_outbox_pending_events_by_topic == ()
