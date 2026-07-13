import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.operations.failure_recovery_gate import (
    RecoveryFieldEvidence,
    RecoveryMode,
    RecoveryPollingEvidence,
    RecoveryResult,
    _compose_command,
    _consumer_lag,
    _evaluate_recovery_result,
    _prepare_failure_recovery_managed_run,
    _resolve_interruption_container,
    _resolve_runtime_connections,
    _set_container_pause,
    _wait_for_full_recovery,
    _write_report,
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


def test_recovery_report_serializes_field_and_terminal_evidence(tmp_path: Path) -> None:
    polling = RecoveryPollingEvidence(
        poll_count=1,
        last_observed_at="2026-07-13T00:00:00+00:00",
        fields=(
            RecoveryFieldEvidence(
                field="transaction_count",
                actual=3,
                expected=2,
                comparison="equals",
                satisfied=False,
                last_changed_at="2026-07-13T00:00:00+00:00",
            ),
        ),
        terminal_reason="transaction_count exceeded exact target: actual=3 expected=2",
    )
    result = RecoveryResult(
        run_id="20260713T000000Z",
        started_at="2026-07-13T00:00:00+00:00",
        ended_at="2026-07-13T00:00:01+00:00",
        interruption_service="portfolio_transaction_processing_service",
        interruption_container_id="container-id",
        requested_interruption_seconds=1,
        actual_interruption_seconds=1.0,
        transaction_topic="transactions.persisted.v1",
        consumer_group="portfolio_transaction_processing_group",
        records_submitted=2,
        source_persistence_seconds=0.1,
        baseline_consumer_lag=0,
        peak_consumer_lag_during_interruption=2,
        consumer_lag_growth=2,
        consumer_lag_after_recovery=1,
        baseline_replay_consumer_lag=0,
        replay_consumer_lag_after_recovery=0,
        transaction_processing_recovery_seconds=None,
        transaction_count=3,
        cost_count=0,
        cashflow_count=0,
        position_count=0,
        processing_claim_count=0,
        dlq_events_added_during_recovery=0,
        recovery_polling=polling,
        recovery_mode=RecoveryMode.FAILED_RECOVERY.value,
        checks_passed=False,
        failed_checks=["recovery polling stopped early"],
    )

    json_path, markdown_path = _write_report(output_dir=tmp_path, result=result)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["recovery_polling"] == {
        "poll_count": 1,
        "last_observed_at": "2026-07-13T00:00:00+00:00",
        "fields": [
            {
                "field": "transaction_count",
                "actual": 3,
                "expected": 2,
                "comparison": "equals",
                "satisfied": False,
                "last_changed_at": "2026-07-13T00:00:00+00:00",
            }
        ],
        "terminal_reason": ("transaction_count exceeded exact target: actual=3 expected=2"),
    }
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "## Recovery field evidence" in markdown
    assert "| transaction_count | 3 | equals | 2 | False |" in markdown
    assert "transaction_count exceeded exact target" in markdown


def test_prepare_failure_recovery_run_owns_integration_runtime_and_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_prepare(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate._load_test_runtime_helpers",
        lambda: (object(), fake_prepare),
    )
    args = SimpleNamespace(
        compose_file="docker-compose.yml",
        compose_project_name="operator-proof-project",
        ingestion_base_url="http://127.0.0.1:18100",
        query_base_url="http://127.0.0.1:18201",
        event_replay_base_url="http://127.0.0.1:18102",
        host_database_url="postgresql://localhost:15432/portfolio_db",
        build=True,
        output_dir="output/task-runs",
        keep_stack_up=True,
        skip_compose=False,
    )

    managed = _prepare_failure_recovery_managed_run(
        args=args,
        repo_root=tmp_path,
    )

    assert managed is sentinel
    assert captured == {
        "profile": "integration",
        "scope": "failure-recovery-gate",
        "compose_project_name": "operator-proof-project",
        "compose_file": tmp_path / "docker-compose.yml",
        "services": (
            "kafka-topic-creator",
            "migration-runner",
            "ingestion_service",
            "query_service",
            "event_replay_service",
            "persistence_service",
            "portfolio_transaction_processing_service",
            "pipeline_orchestrator_service",
        ),
        "build": True,
        "log_path": (tmp_path / "output/task-runs/diagnostics/failure-recovery-gate-compose.log"),
        "endpoint_urls": {
            "E2E_INGESTION_URL": "http://127.0.0.1:18100",
            "E2E_QUERY_URL": "http://127.0.0.1:18201",
            "E2E_EVENT_REPLAY_URL": "http://127.0.0.1:18102",
            "HOST_DATABASE_URL": "postgresql://localhost:15432/portfolio_db",
        },
        "allocate_dynamic_ports": True,
        "keep_stack": True,
    }


def test_prepare_failure_recovery_external_run_preserves_environment_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "existing-operator-stack")
    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate._load_test_runtime_helpers",
        lambda: (
            object(),
            lambda **kwargs: captured.update(kwargs) or object(),
        ),
    )
    args = SimpleNamespace(
        compose_file="docker-compose.yml",
        compose_project_name=None,
        ingestion_base_url=None,
        query_base_url=None,
        event_replay_base_url=None,
        host_database_url=None,
        build=False,
        output_dir="output/task-runs",
        keep_stack_up=False,
        skip_compose=True,
    )

    _prepare_failure_recovery_managed_run(args=args, repo_root=tmp_path)

    assert captured["compose_project_name"] == "existing-operator-stack"
    assert captured["allocate_dynamic_ports"] is False


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


def test_recovery_polling_reports_field_comparison_and_last_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = iter(
        (
            TransactionProcessingCounts(2, 0, 0, 0, 0),
            TransactionProcessingCounts(2, 2, 2, 2, 2),
        )
    )
    lags = iter((2, 0))
    elapsed = 0.0
    observed_at = datetime(2026, 7, 13, tzinfo=UTC)

    def clock() -> float:
        return elapsed

    def sleeper(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    def utc_now() -> datetime:
        return observed_at + timedelta(seconds=elapsed)

    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate.transaction_processing_counts",
        lambda **_kwargs: next(counts),
    )
    store = SimpleNamespace(
        snapshot=lambda **_kwargs: SimpleNamespace(
            partitions=(
                SimpleNamespace(
                    high_watermark=next(lags),
                    committed_offset=0,
                ),
            )
        )
    )

    recovery_seconds, final_counts, final_lag, evidence = _wait_for_full_recovery(
        store=store,
        engine=object(),
        consumer_group="portfolio_transaction_processing_group",
        transaction_topic="transactions.persisted.v1",
        baseline_lag=0,
        portfolio_id="PORTFOLIO_001",
        transaction_id_prefix="TX_TEST",
        expected_records=2,
        timeout_seconds=5,
        clock=clock,
        sleeper=sleeper,
        utc_now=utc_now,
    )

    fields = {field.field: field for field in evidence.fields}
    assert recovery_seconds == 1.0
    assert final_counts == TransactionProcessingCounts(2, 2, 2, 2, 2)
    assert final_lag == 0
    assert evidence.poll_count == 2
    assert evidence.last_observed_at == "2026-07-13T00:00:01+00:00"
    assert fields["transaction_count"].comparison == "equals"
    assert fields["transaction_count"].satisfied is True
    assert fields["transaction_count"].last_changed_at == "2026-07-13T00:00:00+00:00"
    assert fields["cost_count"].last_changed_at == "2026-07-13T00:00:01+00:00"
    assert fields["processing_claim_count"].comparison == "at_least"
    assert fields["consumer_lag"].comparison == "at_most"
    assert all(field.satisfied for field in fields.values())


def test_recovery_polling_reports_unsatisfied_fields_at_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate.transaction_processing_counts",
        lambda **_kwargs: TransactionProcessingCounts(1, 0, 0, 0, 0),
    )
    store = SimpleNamespace(
        snapshot=lambda **_kwargs: SimpleNamespace(
            partitions=(SimpleNamespace(high_watermark=3, committed_offset=0),)
        )
    )

    recovery_seconds, _, _, evidence = _wait_for_full_recovery(
        store=store,
        engine=object(),
        consumer_group="portfolio_transaction_processing_group",
        transaction_topic="transactions.persisted.v1",
        baseline_lag=0,
        portfolio_id="PORTFOLIO_001",
        transaction_id_prefix="TX_TEST",
        expected_records=2,
        timeout_seconds=0,
        clock=lambda: 0.0,
        utc_now=lambda: datetime(2026, 7, 13, tzinfo=UTC),
    )

    mismatches = {field.field: field for field in evidence.fields if not field.satisfied}
    assert recovery_seconds is None
    assert evidence.poll_count == 1
    assert evidence.terminal_reason is None
    assert set(mismatches) == {
        "transaction_count",
        "cost_count",
        "cashflow_count",
        "position_count",
        "processing_claim_count",
        "consumer_lag",
    }
    assert mismatches["transaction_count"].actual == 1
    assert mismatches["transaction_count"].expected == 2
    assert mismatches["consumer_lag"].actual == 3
    assert mismatches["consumer_lag"].expected == 0


def test_recovery_polling_stops_on_terminal_exact_count_overshoot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate.transaction_processing_counts",
        lambda **_kwargs: TransactionProcessingCounts(3, 0, 0, 0, 0),
    )
    store = SimpleNamespace(
        snapshot=lambda **_kwargs: SimpleNamespace(
            partitions=(SimpleNamespace(high_watermark=1, committed_offset=0),)
        )
    )

    recovery_seconds, _, _, evidence = _wait_for_full_recovery(
        store=store,
        engine=object(),
        consumer_group="portfolio_transaction_processing_group",
        transaction_topic="transactions.persisted.v1",
        baseline_lag=0,
        portfolio_id="PORTFOLIO_001",
        transaction_id_prefix="TX_TEST",
        expected_records=2,
        timeout_seconds=30,
        clock=lambda: 0.0,
        sleeper=lambda _seconds: pytest.fail("terminal state must not sleep"),
        utc_now=lambda: datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert recovery_seconds is None
    assert evidence.poll_count == 1
    assert evidence.terminal_reason == (
        "transaction_count exceeded exact target: actual=3 expected=2"
    )


def test_recovery_polling_stops_on_dlq_terminal_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.operations.failure_recovery_gate.transaction_processing_counts",
        lambda **_kwargs: TransactionProcessingCounts(1, 0, 0, 0, 0),
    )
    store = SimpleNamespace(
        snapshot=lambda **_kwargs: SimpleNamespace(
            partitions=(SimpleNamespace(high_watermark=1, committed_offset=0),)
        )
    )

    recovery_seconds, _, _, evidence = _wait_for_full_recovery(
        store=store,
        engine=object(),
        consumer_group="portfolio_transaction_processing_group",
        transaction_topic="transactions.persisted.v1",
        baseline_lag=0,
        portfolio_id="PORTFOLIO_001",
        transaction_id_prefix="TX_TEST",
        expected_records=2,
        timeout_seconds=30,
        terminal_condition=lambda: "DLQ events increased: baseline=0 current=1",
        clock=lambda: 0.0,
        sleeper=lambda _seconds: pytest.fail("DLQ terminal state must not sleep"),
        utc_now=lambda: datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert recovery_seconds is None
    assert evidence.poll_count == 1
    assert evidence.terminal_reason == "DLQ events increased: baseline=0 current=1"


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
