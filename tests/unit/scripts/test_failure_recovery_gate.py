from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.operations.failure_recovery_gate import (
    RecoveryMode,
    _compose_command,
    _consumer_lag,
    _evaluate_recovery_result,
    _resolve_interruption_container,
    _resolve_runtime_connections,
    _set_container_pause,
)
from scripts.operations.transaction_processing_load_support import TransactionProcessingCounts


def _complete_counts(records: int) -> TransactionProcessingCounts:
    return TransactionProcessingCounts(
        transaction_count=records,
        cost_count=records,
        cashflow_count=records,
        position_count=records,
        processing_claim_count=records,
    )


def test_runtime_connections_default_to_generated_isolated_endpoints() -> None:
    endpoints = SimpleNamespace(
        host_database_url="postgresql://localhost:62362/portfolio_db",
        kafka_bootstrap_servers="localhost:62360",
    )

    resolved = _resolve_runtime_connections(
        requested_host_database_url=None,
        requested_kafka_bootstrap_servers=None,
        endpoints=endpoints,
    )

    assert resolved == (
        "postgresql://localhost:62362/portfolio_db",
        "localhost:62360",
    )


def test_runtime_connections_preserve_explicit_operator_overrides() -> None:
    endpoints = SimpleNamespace(
        host_database_url="postgresql://localhost:62362/portfolio_db",
        kafka_bootstrap_servers="localhost:62360",
    )

    resolved = _resolve_runtime_connections(
        requested_host_database_url="postgresql://db.example/core",
        requested_kafka_bootstrap_servers="kafka.example:9092",
        endpoints=endpoints,
    )

    assert resolved == (
        "postgresql://db.example/core",
        "kafka.example:9092",
    )


def test_compose_command_scopes_service_lookup_to_project() -> None:
    assert _compose_command(
        compose_file="docker-compose.yml",
        compose_project_name="core-evidence",
        arguments=["ps", "-q", "portfolio_transaction_processing_service"],
    ) == [
        "docker",
        "compose",
        "-p",
        "core-evidence",
        "-f",
        "docker-compose.yml",
        "ps",
        "-q",
        "portfolio_transaction_processing_service",
    ]


def test_resolve_interruption_container_requires_running_compose_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate._run_capture",
        lambda cmd, cwd: "abc123containerid\n",
    )

    resolved = _resolve_interruption_container(
        repo_root=Path("."),
        compose_file="docker-compose.yml",
        compose_project_name="core-evidence",
        interruption_service="portfolio_transaction_processing_service",
    )

    assert resolved == "abc123containerid"


def test_resolve_interruption_container_fails_closed_when_service_is_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate._run_capture",
        lambda cmd, cwd: "",
    )

    with pytest.raises(RuntimeError, match="Compose service is not running"):
        _resolve_interruption_container(
            repo_root=Path("."),
            compose_file="docker-compose.yml",
            compose_project_name=None,
            interruption_service="portfolio_transaction_processing_service",
        )


def test_set_container_pause_uses_resolved_container_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], Path]] = []
    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate._run_capture",
        lambda cmd, cwd: calls.append((cmd, cwd)) or "",
    )
    repo_root = Path("/tmp/repo")

    _set_container_pause(container_id="container-id", paused=True, repo_root=repo_root)
    _set_container_pause(container_id="container-id", paused=False, repo_root=repo_root)

    assert calls == [
        (["docker", "pause", "container-id"], repo_root),
        (["docker", "unpause", "container-id"], repo_root),
    ]


def test_consumer_lag_treats_uncommitted_partition_as_offset_zero() -> None:
    store = SimpleNamespace(
        snapshot=lambda **kwargs: SimpleNamespace(
            partitions=(
                SimpleNamespace(high_watermark=10, committed_offset=-1001),
                SimpleNamespace(high_watermark=20, committed_offset=15),
            )
        )
    )

    lag = _consumer_lag(
        store=store,
        consumer_group="portfolio_transaction_processing_group",
        transaction_topic="transactions.persisted.v1",
    )

    assert lag == 15


def test_evaluate_recovery_result_requires_exact_domain_and_lag_recovery() -> None:
    mode, failed_checks = _evaluate_recovery_result(
        records_submitted=100,
        baseline_consumer_lag=0,
        consumer_lag_growth=100,
        consumer_lag_after_recovery=0,
        baseline_replay_consumer_lag=0,
        replay_consumer_lag_after_recovery=0,
        transaction_processing_recovery_seconds=12.5,
        max_recovery_seconds=420,
        counts=_complete_counts(100),
        dlq_events_added_during_recovery=0,
    )

    assert mode is RecoveryMode.FULLY_DRAINED
    assert failed_checks == []


def test_evaluate_recovery_result_fails_closed_on_timeout() -> None:
    mode, failed_checks = _evaluate_recovery_result(
        records_submitted=100,
        baseline_consumer_lag=0,
        consumer_lag_growth=100,
        consumer_lag_after_recovery=100,
        baseline_replay_consumer_lag=0,
        replay_consumer_lag_after_recovery=1,
        transaction_processing_recovery_seconds=None,
        max_recovery_seconds=420,
        counts=TransactionProcessingCounts(100, 80, 70, 60, 50),
        dlq_events_added_during_recovery=2,
    )

    assert mode is RecoveryMode.FAILED_RECOVERY
    assert "transaction processing did not fully recover before timeout" in failed_checks
    assert any("consumer lag after recovery" in check for check in failed_checks)
    assert any("replay consumer lag after recovery" in check for check in failed_checks)
    assert any("cost completion count 80" in check for check in failed_checks)
    assert any("cashflow completion count 70" in check for check in failed_checks)
    assert any("position completion count 60" in check for check in failed_checks)
    assert any("claim count 50" in check for check in failed_checks)
    assert any("added 2 DLQ events" in check for check in failed_checks)


def test_evaluate_recovery_result_rejects_unproven_backlog_growth() -> None:
    mode, failed_checks = _evaluate_recovery_result(
        records_submitted=100,
        baseline_consumer_lag=3,
        consumer_lag_growth=99,
        consumer_lag_after_recovery=3,
        baseline_replay_consumer_lag=0,
        replay_consumer_lag_after_recovery=0,
        transaction_processing_recovery_seconds=10,
        max_recovery_seconds=420,
        counts=_complete_counts(100),
        dlq_events_added_during_recovery=0,
    )

    assert mode is RecoveryMode.FAILED_RECOVERY
    assert any("lag growth 99" in check for check in failed_checks)
