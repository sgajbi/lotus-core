import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts.operations import performance_load_gate, transaction_processing_load_support
from scripts.operations.performance_load_gate import (
    _build_transaction_batch,
    _evaluate_profile,
    _write_report,
)


class _MetricsResponse:
    text = (
        "# HELP lotus_core_transaction_processing_operations_total Completed operations.\n"
        "# TYPE lotus_core_transaction_processing_operations_total counter\n"
        'lotus_core_transaction_processing_operations_total{outcome="processed",'
        'stage="transaction"} 120\n'
        'lotus_core_transaction_processing_operations_total{outcome="duplicate",'
        'stage="transaction"} 60\n'
        "# HELP lotus_core_transaction_processing_operation_duration_seconds "
        "Operation duration.\n"
        "# TYPE lotus_core_transaction_processing_operation_duration_seconds histogram\n"
        "lotus_core_transaction_processing_operation_duration_seconds_bucket{"
        'le="0.1",outcome="succeeded",stage="cost"} 80\n'
        "lotus_core_transaction_processing_operation_duration_seconds_bucket{"
        'le="+Inf",outcome="succeeded",stage="cost"} 120\n'
        "lotus_core_transaction_processing_operation_duration_seconds_count{"
        'outcome="succeeded",stage="cost"} 120\n'
        "lotus_core_transaction_processing_operation_duration_seconds_sum{"
        'outcome="succeeded",stage="cost"} 30\n'
        'lotus_core_transaction_processing_operations_total{outcome="succeeded",'
        'stage="cost"} 120\n'
        "# HELP cost_processing_execution_total Cost execution mode.\n"
        "# TYPE cost_processing_execution_total counter\n"
        'cost_processing_execution_total{mode="full_rebuild",cost_basis_method="FIFO"} 120\n'
        "# HELP recalculation_duration_seconds Recalculation duration.\n"
        "# TYPE recalculation_duration_seconds histogram\n"
        'recalculation_duration_seconds_bucket{le="+Inf"} 120\n'
        "recalculation_duration_seconds_count 120\n"
        "recalculation_duration_seconds_sum 6\n"
        "# HELP recalculation_depth Recalculation depth.\n"
        "# TYPE recalculation_depth histogram\n"
        'recalculation_depth_bucket{le="+Inf"} 120\n'
        "recalculation_depth_count 120\n"
        "recalculation_depth_sum 120\n"
        "# HELP cost_processing_open_lots_restored Restored lots.\n"
        "# TYPE cost_processing_open_lots_restored histogram\n"
        'cost_processing_open_lots_restored_count{cost_basis_method="FIFO"} 20\n'
        'cost_processing_open_lots_restored_sum{cost_basis_method="FIFO"} 30\n'
        "# HELP db_operation_latency_seconds Database operation duration.\n"
        "# TYPE db_operation_latency_seconds histogram\n"
        'db_operation_latency_seconds_bucket{le="+Inf",method="save",'
        'repository="PositionRepository"} 120\n'
        'db_operation_latency_seconds_count{method="save",'
        'repository="PositionRepository"} 120\n'
        'db_operation_latency_seconds_sum{method="save",'
        'repository="PositionRepository"} 24\n'
        'db_operation_latency_seconds_count{method="load",'
        'repository="CostRepository"} 60\n'
        'db_operation_latency_seconds_sum{method="load",'
        'repository="CostRepository"} 18\n'
        'db_operation_latency_seconds_count{method="incomplete",'
        'repository="IgnoredRepository"} 1\n'
    )

    def raise_for_status(self) -> None:
        return None


def test_transaction_processing_operation_count_reads_bounded_duplicate_metric(
    monkeypatch,
) -> None:
    requested: list[tuple[str, int]] = []

    def get(url: str, *, timeout: int) -> _MetricsResponse:
        requested.append((url, timeout))
        return _MetricsResponse()

    monkeypatch.setattr(transaction_processing_load_support.requests, "get", get)

    count = transaction_processing_load_support.transaction_processing_operation_count(
        transaction_processing_base_url="http://localhost:8090",
        stage="transaction",
        outcome="duplicate",
    )

    assert count == 60
    assert requested == [("http://localhost:8090/metrics", 10)]


def test_transaction_processing_operation_evidence_retains_bounded_stage_timing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        transaction_processing_load_support.requests,
        "get",
        lambda _url, *, timeout: _MetricsResponse(),
    )

    evidence = transaction_processing_load_support.transaction_processing_operation_evidence(
        transaction_processing_base_url="http://localhost:8090"
    )

    cost = next(item for item in evidence if item.stage == "cost")
    assert cost.outcome == "succeeded"
    assert cost.operation_count == 120
    assert cost.duration_observation_count == 120
    assert cost.total_duration_seconds == 30.0
    assert cost.average_duration_seconds == 0.25
    duplicate = next(item for item in evidence if item.outcome == "duplicate")
    assert duplicate.operation_count == 60
    assert duplicate.duration_observation_count == 0
    assert duplicate.average_duration_seconds is None


def test_cost_processing_runtime_evidence_retains_existing_bounded_metrics(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        transaction_processing_load_support.requests,
        "get",
        lambda _url, *, timeout: _MetricsResponse(),
    )

    evidence = transaction_processing_load_support.cost_processing_runtime_evidence(
        transaction_processing_base_url="http://localhost:8090"
    )

    assert evidence.executions[0].mode == "full_rebuild"
    assert evidence.executions[0].cost_basis_method == "FIFO"
    assert evidence.executions[0].operation_count == 120
    assert evidence.recalculation_duration_seconds is not None
    assert evidence.recalculation_duration_seconds.observation_count == 120
    assert evidence.recalculation_duration_seconds.total == 6.0
    assert evidence.recalculation_duration_seconds.average == 0.05
    assert evidence.recalculation_depth is not None
    assert evidence.recalculation_depth.average == 1.0
    assert evidence.restored_open_lots[0].cost_basis_method == "FIFO"
    assert evidence.restored_open_lots[0].average == 1.5


def test_database_operation_evidence_retains_sorted_bounded_repository_timings(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        transaction_processing_load_support.requests,
        "get",
        lambda _url, *, timeout: _MetricsResponse(),
    )

    evidence = transaction_processing_load_support.database_operation_evidence(
        transaction_processing_base_url="http://localhost:8090"
    )

    assert [(item.repository, item.method) for item in evidence] == [
        ("CostRepository", "load"),
        ("PositionRepository", "save"),
    ]
    assert evidence[0].observation_count == 60
    assert evidence[0].total_duration_seconds == 18.0
    assert evidence[0].average_duration_seconds == 0.3
    assert evidence[1].observation_count == 120
    assert evidence[1].average_duration_seconds == 0.2


def test_successful_terminal_count_includes_processed_and_duplicate_outcomes(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        transaction_processing_load_support.requests,
        "get",
        lambda _url, *, timeout: _MetricsResponse(),
    )

    count = transaction_processing_load_support.successful_transaction_delivery_count(
        transaction_processing_base_url="http://localhost:8090"
    )

    assert count == 180


def test_wait_for_successful_terminal_count_accepts_safe_duplicate_completion(
    monkeypatch,
) -> None:
    observed_urls: list[str] = []

    def count(*, transaction_processing_base_url: str) -> int:
        observed_urls.append(transaction_processing_base_url)
        return 180

    monkeypatch.setattr(
        transaction_processing_load_support,
        "successful_transaction_delivery_count",
        count,
    )
    monkeypatch.setattr(
        transaction_processing_load_support.time,
        "sleep",
        lambda _seconds: pytest.fail("completed terminal work must not sleep"),
    )

    wait_for_terminal_count = (
        transaction_processing_load_support.wait_for_successful_transaction_deliveries
    )
    elapsed = wait_for_terminal_count(
        transaction_processing_base_url="http://localhost:8090",
        expected_minimum=180,
        timeout_seconds=1,
    )

    assert elapsed is not None
    assert 0 <= elapsed < 1
    assert observed_urls == ["http://localhost:8090"]


def test_repair_replay_completion_uses_successful_terminal_outcomes(monkeypatch) -> None:
    counted: list[str] = []
    waited: list[tuple[str, int, int]] = []

    def count(*, transaction_processing_base_url: str) -> int:
        counted.append(transaction_processing_base_url)
        return 41

    def wait(
        *,
        transaction_processing_base_url: str,
        expected_minimum: int,
        timeout_seconds: int,
    ) -> float:
        waited.append(
            (
                transaction_processing_base_url,
                expected_minimum,
                timeout_seconds,
            )
        )
        return 2.5

    monkeypatch.setattr(performance_load_gate, "_successful_terminal_count", count)
    monkeypatch.setattr(performance_load_gate, "_wait_for_terminal_count", wait)

    baseline = performance_load_gate._repair_replay_completion_count(
        transaction_processing_base_url="http://localhost:8090"
    )
    drain_seconds = performance_load_gate._wait_for_repair_replay_completion(
        transaction_processing_base_url="http://localhost:8090",
        expected_minimum=45,
        timeout_seconds=180,
    )

    assert baseline == 41
    assert drain_seconds == 2.5
    assert counted == ["http://localhost:8090"]
    assert waited == [("http://localhost:8090", 45, 180)]


def test_transaction_batch_uses_the_seeded_portfolio_and_instrument_namespace() -> None:
    rows = _build_transaction_batch(
        portfolio_id="PERF_LOAD_RUN1",
        batch_size=2,
        seed="PERF-RUN1-steady",
        transaction_date="2026-07-10T09:00:00Z",
        security_prefix="PERF_RUN1_SEC",
    )

    assert {row["portfolio_id"] for row in rows} == {"PERF_LOAD_RUN1"}
    assert [row["security_id"] for row in rows] == [
        "PERF_RUN1_SEC_000",
        "PERF_RUN1_SEC_001",
    ]
    assert [row["instrument_id"] for row in rows] == [
        "PERF_RUN1_SEC_000",
        "PERF_RUN1_SEC_001",
    ]
    assert {row["transaction_date"] for row in rows} == {"2026-07-10T09:00:00Z"}


def test_evaluate_profile_requires_transaction_processing_drain_when_governed() -> None:
    result = _evaluate_profile(
        profile_name="steady_state",
        records_submitted=10,
        batches_submitted=1,
        started_at=10.0,
        ended_at=20.0,
        baseline_health={
            "summary": {"backlog_jobs": 0},
            "slo": {"backlog_age_seconds": 0.0},
            "error_budget": {
                "dlq_events_in_window": 0,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0",
            },
        },
        health={
            "summary": {"backlog_jobs": 0},
            "slo": {"backlog_age_seconds": 0.0},
            "error_budget": {
                "dlq_events_in_window": 0,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0",
            },
        },
        drain_seconds=None,
        thresholds={
            "min_throughput_rps": 0.5,
            "max_backlog_age_increase_seconds": 1.0,
            "max_dlq_pressure_ratio_added": 0.0,
            "max_replay_pressure_ratio_increase": 0.0,
            "max_drain_seconds": None,
            "require_drain": True,
        },
    )

    assert result.checks_passed is False
    assert "transaction_processing_drain timeout" in result.failed_checks


def test_evaluate_profile_uses_incremental_health_pressure_against_baseline() -> None:
    result = _evaluate_profile(
        profile_name="steady_state",
        records_submitted=100,
        batches_submitted=2,
        started_at=10.0,
        ended_at=20.0,
        baseline_health={
            "summary": {"backlog_jobs": 64},
            "slo": {"backlog_age_seconds": 1200.0},
            "error_budget": {
                "dlq_events_in_window": 118,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0128",
            },
        },
        health={
            "summary": {"backlog_jobs": 68},
            "slo": {"backlog_age_seconds": 1260.0},
            "error_budget": {
                "dlq_events_in_window": 118,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0131",
            },
        },
        drain_seconds=None,
        thresholds={
            "min_throughput_rps": 5.0,
            "max_backlog_age_increase_seconds": 120.0,
            "max_dlq_pressure_ratio_added": 0.5,
            "max_replay_pressure_ratio_increase": 0.01,
            "max_drain_seconds": None,
        },
    )

    assert result.checks_passed is True
    assert result.backlog_jobs_growth_during_profile == 4
    assert result.backlog_age_increase_seconds == 60.0
    assert result.dlq_events_added_during_profile == 0
    assert result.dlq_pressure_ratio_added == 0.0
    assert result.replay_pressure_ratio_increase == 0.0003


def test_evaluate_profile_fails_when_incremental_pressure_breaches_thresholds() -> None:
    result = _evaluate_profile(
        profile_name="burst",
        records_submitted=10,
        batches_submitted=1,
        started_at=10.0,
        ended_at=20.0,
        baseline_health={
            "summary": {"backlog_jobs": 8},
            "slo": {"backlog_age_seconds": 15.0},
            "error_budget": {
                "dlq_events_in_window": 2,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0500",
            },
        },
        health={
            "summary": {"backlog_jobs": 18},
            "slo": {"backlog_age_seconds": 175.0},
            "error_budget": {
                "dlq_events_in_window": 9,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.4000",
            },
        },
        drain_seconds=None,
        thresholds={
            "min_throughput_rps": 2.0,
            "max_backlog_age_increase_seconds": 60.0,
            "max_dlq_pressure_ratio_added": 0.5,
            "max_replay_pressure_ratio_increase": 0.2,
            "max_drain_seconds": None,
        },
    )

    assert result.checks_passed is False
    assert "backlog_age_increase 160.00 > max 60.00" in result.failed_checks
    assert "dlq_pressure_added 0.7000 > max 0.5000" in result.failed_checks
    assert "replay_pressure_increase 0.3500 > max 0.2000" in result.failed_checks


def test_write_report_persists_profile_tier(tmp_path) -> None:
    result = _evaluate_profile(
        profile_name="steady_state",
        records_submitted=100,
        batches_submitted=2,
        started_at=10.0,
        ended_at=20.0,
        baseline_health={
            "summary": {"backlog_jobs": 0},
            "slo": {"backlog_age_seconds": 0.0},
            "error_budget": {
                "dlq_events_in_window": 0,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0000",
            },
        },
        health={
            "summary": {"backlog_jobs": 0},
            "slo": {"backlog_age_seconds": 0.0},
            "error_budget": {
                "dlq_events_in_window": 0,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0000",
            },
        },
        drain_seconds=None,
        thresholds={
            "min_throughput_rps": 1.0,
            "max_backlog_age_increase_seconds": 60.0,
            "max_dlq_pressure_ratio_added": 0.5,
            "max_replay_pressure_ratio_increase": 0.1,
            "max_drain_seconds": None,
        },
    )

    json_path, md_path = _write_report(
        output_dir=tmp_path,
        run_id="RUN1",
        profile_tier="full",
        results=[result],
        enforce=True,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert payload["profile_tier"] == "full"
    assert "- Profile tier: full" in markdown
    assert "Throughput boundary: ingestion start through combined cost" in markdown
    assert "Transaction drain sec" in markdown


def test_main_reenters_under_managed_dynamic_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for environment_key in (
        "E2E_INGESTION_URL",
        "E2E_QUERY_URL",
        "E2E_EVENT_REPLAY_URL",
        "E2E_TRANSACTION_PROCESSING_URL",
        "HOST_DATABASE_URL",
    ):
        monkeypatch.delenv(environment_key, raising=False)
    args = SimpleNamespace(
        repo_root=str(tmp_path),
        compose_file="docker-compose.yml",
        ingestion_base_url=None,
        query_base_url=None,
        event_replay_base_url=None,
        transaction_processing_base_url=None,
        host_database_url=None,
        skip_compose=False,
        build=False,
        compose_log_path="output/task-runs/diagnostics/performance-load.log",
        keep_compose=False,
    )
    managed_run = MagicMock()
    replacement_endpoints = SimpleNamespace(
        e2e_ingestion_url="http://localhost:26000",
        e2e_query_url="http://localhost:26001",
        e2e_event_replay_url="http://localhost:26009",
        e2e_transaction_processing_url="http://localhost:26090",
        host_database_url="postgresql://user:password@localhost:26432/portfolio_db",
    )

    def _enter_managed_run() -> object:
        managed_run.runtime.endpoints = replacement_endpoints
        return managed_run

    managed_run.__enter__.side_effect = _enter_managed_run
    managed_run.__exit__.return_value = False
    managed_run.runtime.endpoints = SimpleNamespace(
        e2e_ingestion_url="http://localhost:16000",
        e2e_query_url="http://localhost:16001",
        e2e_event_replay_url="http://localhost:16009",
        e2e_transaction_processing_url="http://localhost:16090",
        host_database_url="postgresql://user:password@localhost:16432/portfolio_db",
    )
    prepared: list[dict[str, object]] = []
    reentered: list[tuple[object, object]] = []
    original_main = performance_load_gate.main

    monkeypatch.setattr(
        performance_load_gate,
        "prepare_managed_compose_run",
        lambda **kwargs: prepared.append(kwargs) or managed_run,
    )
    monkeypatch.setattr(
        performance_load_gate,
        "main",
        lambda args, managed: reentered.append((args, managed)) or 0,
    )

    assert original_main(args, None) == 0
    assert prepared[0]["scope"] == "performance-load-gate"
    assert prepared[0]["services"] == tuple(performance_load_gate.PERFORMANCE_GATE_SERVICES)
    assert args.ingestion_base_url == "http://localhost:26000"
    assert args.transaction_processing_base_url == "http://localhost:26090"
    assert args.host_database_url.endswith("localhost:26432/portfolio_db")
    assert reentered == [(args, managed_run)]
