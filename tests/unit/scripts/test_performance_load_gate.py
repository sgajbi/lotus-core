import json
import multiprocessing
import os
import re
import subprocess
import sys
import time
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts.operations import performance_load_gate, transaction_processing_load_support
from scripts.operations.performance import load_completion_diagnostics
from scripts.operations.performance_load_gate import (
    DRAIN_OBSERVATION_TIMEOUT_SECONDS,
    GOVERNED_LOAD_PORTFOLIO_ID,
    GOVERNED_LOAD_SECURITY_COUNT,
    GOVERNED_LOAD_SECURITY_PREFIX,
    GOVERNED_MAX_DRAIN_SECONDS,
    MAX_GOVERNED_KEYS_PER_PARTITION,
    TRANSACTION_TOPIC_PARTITIONS,
    _build_transaction_batch,
    _evaluate_profile,
    _governed_partition_distribution,
    _next_transaction_timestamp,
    _validate_governed_load_identity,
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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size):
        yield self.text.encode()


def test_reference_seed_carries_governed_load_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    post = MagicMock(return_value=SimpleNamespace(status_code=202, text=""))
    monkeypatch.setattr(transaction_processing_load_support.requests, "post", post)

    transaction_processing_load_support._post_ingestion_records(
        ingestion_base_url="http://ingestion",
        endpoint="/ingest/business-dates",
        root_key="business_dates",
        rows=[{"business_date": "2026-08-08"}],
    )

    assert post.call_args.kwargs["headers"] == {
        "X-Tenant-Id": transaction_processing_load_support.LOAD_TENANT_ID
    }


def test_transaction_processing_operation_count_reads_bounded_duplicate_metric(
    monkeypatch,
) -> None:
    requested: list[tuple[str, int]] = []

    def get(url: str, *, timeout: int, stream: bool = False) -> _MetricsResponse:
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


def test_transaction_processing_timeout_reports_final_domain_counts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        transaction_processing_load_support,
        "transaction_processing_counts",
        lambda **_kwargs: SimpleNamespace(
            transaction_count=640,
            cost_count=640,
            cashflow_count=640,
            position_count=639,
            processing_claim_count=839,
        ),
    )

    drain_seconds = transaction_processing_load_support.wait_for_transaction_processing(
        engine=MagicMock(),
        portfolio_id="PERF_BALANCED_V1",
        transaction_id_prefix="TX_PERF-burst",
        expected=640,
        expected_processing_claim_minimum=840,
        timeout_seconds=0,
    )

    assert drain_seconds is None
    output = capsys.readouterr().out
    assert "transaction_count=640" in output
    assert "position_count=639" in output
    assert "processing_claim_count=839" in output


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
    assert evidence[0].runtime == "portfolio-transaction-processing"
    assert evidence[0].total_duration_seconds == 18.0
    assert evidence[0].average_duration_seconds == 0.3
    assert evidence[1].observation_count == 120
    assert evidence[1].average_duration_seconds == 0.2


def test_database_operation_evidence_binds_samples_to_the_scraped_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        transaction_processing_load_support.requests,
        "get",
        lambda _url, *, timeout: _MetricsResponse(),
    )

    evidence = transaction_processing_load_support.runtime_database_operation_evidence(
        runtime="portfolio-derived-state",
        metrics_base_url="http://localhost:8085",
    )

    assert evidence
    assert {item.runtime for item in evidence} == {"portfolio-derived-state"}


def test_database_operation_evidence_rejects_unbounded_runtime_before_scrape(monkeypatch) -> None:
    get = MagicMock()
    monkeypatch.setattr(transaction_processing_load_support.requests, "get", get)

    with pytest.raises(ValueError, match="Unsupported database-operation runtime"):
        transaction_processing_load_support.runtime_database_operation_evidence(
            runtime="portfolio-42",
            metrics_base_url="http://localhost:8085",
        )

    get.assert_not_called()


def test_repair_replay_completion_uses_processed_transaction_outcome(monkeypatch) -> None:
    counted: list[tuple[str, str, str]] = []
    waited: list[tuple[str, str, str, int, int]] = []

    def count(*, transaction_processing_base_url: str, stage: str, outcome: str) -> dict:
        counted.append((transaction_processing_base_url, stage, outcome))
        return {"status": "observed", "count": 41, "labels": {"stage": stage, "outcome": outcome}}

    def wait(
        *,
        transaction_processing_base_url: str,
        stage: str,
        outcome: str,
        expected_minimum: int,
        timeout_seconds: int,
        baseline: dict,
        on_observation,
        on_pending_observation,
    ) -> float:
        waited.append(
            (
                transaction_processing_base_url,
                stage,
                outcome,
                expected_minimum,
                timeout_seconds,
            )
        )
        return 2.5

    monkeypatch.setattr(
        performance_load_gate, "_transaction_processing_operation_observation", count
    )
    monkeypatch.setattr(performance_load_gate, "_wait_for_operation_count", wait)

    baseline = performance_load_gate._repair_replay_completion_count(
        transaction_processing_base_url="http://localhost:8090"
    )
    drain_seconds = performance_load_gate._wait_for_repair_replay_completion(
        transaction_processing_base_url="http://localhost:8090",
        expected_minimum=45,
        timeout_seconds=180,
        baseline=baseline,
        on_observation=lambda observation: None,
    )

    assert baseline["count"] == 41
    assert drain_seconds == 2.5
    assert counted == [("http://localhost:8090", "transaction", "processed")]
    assert waited == [("http://localhost:8090", "transaction", "processed", 45, 180)]


def test_replay_storm_counts_only_accepted_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            SimpleNamespace(
                status_code=202,
                text="",
                json=lambda: {"accepted_count": 2},
            ),
            SimpleNamespace(
                status_code=409,
                text='{"detail":{"code":"INGESTION_REPLAY_BLOCKED"}}',
            ),
        ]
    )
    post = MagicMock(side_effect=lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(performance_load_gate.requests, "post", post)

    accepted = performance_load_gate._trigger_replay_storm(
        ingestion_base_url="http://ingestion",
        transaction_ids=["TX-1", "TX-2"],
        bursts=2,
        burst_size=2,
    )

    assert accepted == 2
    assert all(
        call.kwargs["headers"] == performance_load_gate.LOAD_TENANT_HEADERS
        for call in post.call_args_list
    )


def test_health_snapshot_combines_tenant_and_operator_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get = MagicMock(
        side_effect=[
            SimpleNamespace(status_code=200, json=lambda: {"backlog": 0}),
            SimpleNamespace(status_code=200, json=lambda: {"slo": "met"}),
            SimpleNamespace(status_code=200, json=lambda: {"budget": "healthy"}),
        ]
    )
    monkeypatch.setattr(performance_load_gate.requests, "get", get)

    snapshot = performance_load_gate._get_health_snapshot(
        event_replay_base_url="http://event-replay",
        ops_token="ops-token",
    )

    assert snapshot["summary"] == {"backlog": 0}
    assert all(
        call.kwargs["headers"]
        == {
            "X-Tenant-Id": transaction_processing_load_support.LOAD_TENANT_ID,
            "X-Lotus-Ops-Token": "ops-token",
        }
        for call in get.call_args_list
    )


def test_replay_storm_rejects_untruthful_accepted_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        performance_load_gate.requests,
        "post",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=202,
            text="",
            json=lambda: {"accepted_count": 3},
        ),
    )

    with pytest.raises(RuntimeError, match="invalid accepted_count"):
        performance_load_gate._trigger_replay_storm(
            ingestion_base_url="http://ingestion",
            transaction_ids=["TX-1", "TX-2"],
            bursts=1,
            burst_size=2,
        )


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
    assert [row["transaction_date"] for row in rows] == [
        "2026-07-10T09:00:00Z",
        "2026-07-10T09:00:00.000001Z",
    ]


def test_transaction_batches_preserve_monotonic_tie_break_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted_transaction_ids: list[str] = []
    posted_transaction_timestamps: list[str] = []

    def post(
        _url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> SimpleNamespace:
        assert timeout == 30
        assert headers == {"X-Tenant-Id": transaction_processing_load_support.LOAD_TENANT_ID}
        transactions = json["transactions"]
        assert isinstance(transactions, list)
        posted_transaction_ids.extend(row["transaction_id"] for row in transactions)
        posted_transaction_timestamps.extend(row["transaction_date"] for row in transactions)
        return SimpleNamespace(status_code=202, text="")

    monkeypatch.setattr(transaction_processing_load_support.requests, "post", post)

    transaction_ids, batches_submitted = transaction_processing_load_support.ingest_transactions(
        ingestion_base_url="http://ingestion",
        portfolio_id="PERF_BALANCED_V1",
        batches=2,
        batch_size=2,
        sleep_seconds_between_batches=0.0,
        seed_prefix="PERF-RUN-burst",
        security_prefix="PERF_CANONICAL_V1_SEC",
        transaction_date="2026-08-08T09:00:00Z",
        sequence_offset=10,
    )

    assert batches_submitted == 2
    assert (
        transaction_ids
        == posted_transaction_ids
        == [
            "TX_PERF-RUN-burst-000-0000",
            "TX_PERF-RUN-burst-000-0001",
            "TX_PERF-RUN-burst-001-0000",
            "TX_PERF-RUN-burst-001-0001",
        ]
    )
    assert transaction_ids == sorted(transaction_ids)
    assert posted_transaction_timestamps == [
        "2026-08-08T09:00:00.000010Z",
        "2026-08-08T09:00:00.000011Z",
        "2026-08-08T09:00:00.000012Z",
        "2026-08-08T09:00:00.000013Z",
    ]


def test_governed_load_identity_is_stable_and_partition_balanced() -> None:
    distribution = _governed_partition_distribution()

    assert GOVERNED_LOAD_PORTFOLIO_ID == "PERF_BALANCED_V1"
    assert GOVERNED_LOAD_SECURITY_PREFIX == "PERF_CANONICAL_V1_SEC"
    assert TRANSACTION_TOPIC_PARTITIONS == 12
    assert len(distribution) == TRANSACTION_TOPIC_PARTITIONS
    assert sum(distribution) == GOVERNED_LOAD_SECURITY_COUNT == 20
    assert max(distribution) == MAX_GOVERNED_KEYS_PER_PARTITION == 2
    assert distribution == (1, 2, 2, 2, 2, 1, 1, 1, 2, 2, 2, 2)


def test_governed_load_identity_fails_closed_after_partition_capacity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(performance_load_gate, "TRANSACTION_TOPIC_PARTITIONS", 4)

    with pytest.raises(RuntimeError, match="exceed the governed per-partition bound"):
        _validate_governed_load_identity()


def test_next_transaction_timestamp_appends_after_reused_stack_history() -> None:
    latest_timestamp = datetime(2026, 8, 8, 9, 0, 0, 839, tzinfo=UTC)
    result = MagicMock()
    result.scalar_one_or_none.return_value = latest_timestamp
    connection = MagicMock()
    connection.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection

    next_timestamp = _next_transaction_timestamp(
        engine=engine,
        default_timestamp=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
    )

    assert next_timestamp == datetime(2026, 8, 8, 9, 0, 0, 840, tzinfo=UTC)
    assert connection.execute.call_args.args[1] == {"portfolio_id": GOVERNED_LOAD_PORTFOLIO_ID}


def test_next_transaction_timestamp_uses_default_for_a_clean_stack() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    connection = MagicMock()
    connection.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    default_timestamp = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)

    assert (
        _next_transaction_timestamp(engine=engine, default_timestamp=default_timestamp)
        == default_timestamp
    )


def test_next_transaction_timestamp_rejects_an_invalid_database_value() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = "2026-08-08T09:00:00Z"
    connection = MagicMock()
    connection.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection

    with pytest.raises(RuntimeError, match="unexpected type: str"):
        _next_transaction_timestamp(
            engine=engine,
            default_timestamp=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
        )


def test_governed_drain_slos_are_stricter_than_the_observation_window() -> None:
    assert DRAIN_OBSERVATION_TIMEOUT_SECONDS == 240
    assert GOVERNED_MAX_DRAIN_SECONDS == {
        "fast": {
            "steady_state": 60.0,
            "burst": 120.0,
            "replay_storm": 120.0,
        },
        "full": {
            "steady_state": 60.0,
            "burst": 180.0,
            "replay_storm": 180.0,
        },
    }
    assert all(
        max_drain < DRAIN_OBSERVATION_TIMEOUT_SECONDS
        for tier in GOVERNED_MAX_DRAIN_SECONDS.values()
        for max_drain in tier.values()
    )


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
    args = Namespace(
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

    def prepare(**kwargs):
        prepared.append(kwargs)
        return managed_run

    def reenter(args, managed):
        reentered.append((args, managed))
        return 0

    monkeypatch.setattr(performance_load_gate, "prepare_managed_compose_run", prepare)
    monkeypatch.setattr(performance_load_gate, "main", reenter)

    assert original_main(args, None) == 0
    assert prepared[0]["scope"] == "performance-load-gate"
    assert prepared[0]["services"] == tuple(performance_load_gate.PERFORMANCE_GATE_SERVICES)
    managed_run.runtime.export_to.assert_called_once_with(os.environ)
    assert args.ingestion_base_url == "http://localhost:26000"
    assert args.transaction_processing_base_url == "http://localhost:26090"
    assert args.host_database_url.endswith("localhost:26432/portfolio_db")
    assert reentered == [(args, managed_run)]


@pytest.fixture
def load_boundary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Exercise real main/report sequencing without any runtime or network."""
    args = SimpleNamespace(
        repo_root=str(tmp_path),
        output_dir="reports",
        profile_tier="full",
        enforce=True,
        skip_compose=True,
        ready_timeout_seconds=1,
        drain_timeout_seconds=240,
        ingestion_base_url="http://isolated-ingestion",
        query_base_url="http://isolated-query",
        event_replay_base_url="http://isolated-replay",
        transaction_processing_base_url="http://isolated-ptp",
        host_database_url="postgresql://user:secret@localhost:5432/portfolio_db",
        ops_token="secret",
    )
    engine = MagicMock()
    engine.url.render_as_string.return_value = args.host_database_url
    for name in ("_wait_ready", "_seed_load_context"):
        monkeypatch.setattr(performance_load_gate, name, lambda **kwargs: None)
    monkeypatch.setattr(
        performance_load_gate, "create_sync_database_engine", lambda **kwargs: engine
    )
    monkeypatch.setattr(
        performance_load_gate,
        "_next_transaction_timestamp",
        lambda **kwargs: datetime(2026, 10, 5, tzinfo=UTC),
    )
    monkeypatch.setattr(
        performance_load_gate,
        "_get_health_snapshot",
        lambda **kwargs: {
            "summary": {"backlog_jobs": 0},
            "slo": {"backlog_age_seconds": 0},
            "error_budget": {
                "dlq_events_in_window": 0,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": 0,
            },
        },
    )
    monkeypatch.setattr(performance_load_gate, "_processed_event_count", lambda **kwargs: 9000)
    monkeypatch.setattr(transaction_processing_load_support.time, "sleep", lambda seconds: None)
    response = MagicMock(status_code=202)
    response.json.return_value = {"job_id": "load-job", "correlation_id": "load-correlation"}
    monkeypatch.setattr(performance_load_gate.requests, "post", lambda *args, **kwargs: response)
    monkeypatch.setattr(
        performance_load_gate,
        "_repair_replay_completion_count",
        lambda **kwargs: {
            "status": "observed",
            "count": 0,
            "labels": {"stage": "transaction", "outcome": "processed"},
            "producer_birth": 123,
        },
    )
    replay = MagicMock(return_value=360)
    monkeypatch.setattr(performance_load_gate, "_trigger_replay_storm", replay)
    monkeypatch.setattr(
        performance_load_gate, "_wait_for_repair_replay_completion", lambda **kwargs: 1
    )
    return args, replay, tmp_path


def _retained_report(tmp_path: Path) -> dict:
    payload: dict = json.loads(next((tmp_path / "reports").glob("*.json")).read_text())
    return payload


def test_main_enables_private_capture_before_first_governed_seed_delivery(
    load_boundary, monkeypatch
):
    args, _replay, _tmp_path = load_boundary
    events = []

    def enable(args, managed):
        events.append("enable")
        return {"status": "enabled", "generation": "a" * 32}

    def seed(**kwargs):
        assert events == ["enable"]
        events.append("seed")
        raise RuntimeError("stop before any governed delivery")

    monkeypatch.setattr(performance_load_gate, "_enable_owned_processing_phases", enable)
    monkeypatch.setattr(performance_load_gate, "_seed_load_context", seed)
    with pytest.raises(RuntimeError, match="stop before any governed delivery"):
        performance_load_gate.main(args)
    assert events == ["enable", "seed"]


def test_main_source_timeout_preserves_partial_results_and_exact_inputs(load_boundary, monkeypatch):
    args, replay, tmp_path = load_boundary
    drains = iter([1.0, None, None])
    counts = transaction_processing_load_support.TransactionProcessingCounts(24, 24, 24, 24, 9000)

    def wait(**kwargs):
        value = next(drains)
        if value is None:
            kwargs["on_timeout"](counts)
        return value

    monkeypatch.setattr(performance_load_gate, "_wait_for_transaction_processing", wait)
    monkeypatch.setattr(
        performance_load_gate,
        "collect_load_completion_diagnostics",
        lambda **kwargs: {"status": "unavailable", "reason": "no_interface"},
    )
    with pytest.raises(
        TimeoutError, match="Replay source transactions did not complete before replay"
    ):
        performance_load_gate.main(args)
    report = _retained_report(tmp_path)
    assert report["overall_passed"] is False
    assert [p["records_submitted"] for p in report["profiles"]] == [200, 640]
    assert report["profiles"][0]["checks_passed"] is True
    assert report["profiles"][1]["checks_passed"] is False
    evidence = report["completion_evidence"]
    assert evidence["stage"] == "replay_source"
    assert evidence["replay_storm_status"] == "not_run"
    assert evidence["profiles_not_run"] == ["replay_storm"]
    batches = evidence["submitted_batches"]
    assert [
        sum(b["submitted_count"] for b in batches[name])
        for name in ("steady_state", "burst", "replay_source")
    ] == [200, 640, 120]
    assert (
        len(
            {
                identifier
                for group in batches.values()
                for b in group
                for identifier in b["submitted_ids"]
            }
        )
        == 960
    )
    assert evidence["source_timeouts"][1]["drain_deadline_counts"]["transaction_count"] == 24
    assert evidence["source_timeouts"][1]["claims_scope"] == "portfolio_aggregate_not_exact_prefix"
    replay.assert_not_called()


def test_main_success_keeps_original_workload_and_admission(load_boundary, monkeypatch):
    args, replay, tmp_path = load_boundary
    wait = MagicMock(return_value=1.0)
    monkeypatch.setattr(performance_load_gate, "_wait_for_transaction_processing", wait)
    collector = MagicMock()
    monkeypatch.setattr(performance_load_gate, "collect_load_completion_diagnostics", collector)
    assert performance_load_gate.main(args) == 0
    assert [call.kwargs["expected"] for call in wait.call_args_list] == [200, 640, 120]
    assert all(call.kwargs["timeout_seconds"] == 240 for call in wait.call_args_list)
    report = _retained_report(tmp_path)
    assert report["overall_passed"] is True
    assert report["completion_evidence"]["replay_storm_status"] == "completed"
    assert report["completion_evidence"]["profiles_not_run"] == []
    replay.assert_called_once()
    collector.assert_not_called()


@pytest.mark.parametrize("drain_seconds", [213.052, None])
def test_main_active_boundary_preserves_completed_breach_or_timeout_verdict(
    load_boundary, monkeypatch, drain_seconds
):
    args, _, tmp_path = load_boundary
    monkeypatch.setattr(
        performance_load_gate, "_wait_for_transaction_processing", lambda **kwargs: 1
    )
    diagnostic = {"status": "observed", "probes": {"active": "earlier_snapshot"}}
    child = MagicMock()
    child.finish.return_value = diagnostic
    start = MagicMock(return_value=child)
    timeout_collector = MagicMock()
    monkeypatch.setattr(performance_load_gate, "start_load_completion_diagnostics", start)
    monkeypatch.setattr(
        performance_load_gate, "collect_load_completion_diagnostics", timeout_collector
    )

    def wait(**kwargs):
        pending = {
            "status": "observed",
            "continuity": "observed",
            "count": 200,
            "labels": {"stage": "transaction", "outcome": "processed"},
            "producer_birth": 123,
        }
        kwargs["on_pending_observation"](pending, 180)
        kwargs["on_pending_observation"](pending, 200)
        kwargs["on_observation"]({**pending, "count": 360 if drain_seconds else 200})
        return drain_seconds

    monkeypatch.setattr(performance_load_gate, "_wait_for_repair_replay_completion", wait)
    assert performance_load_gate.main(args) == 1
    retained = _retained_report(tmp_path)
    assert retained["overall_passed"] is False
    completion = retained["completion_evidence"]["replay_completion"]
    assert completion["slo_boundary_capture"]["diagnostics"] == diagnostic
    assert completion["slo_boundary_capture"]["observation"]["count"] == 200
    assert retained["completion_evidence"]["status"] == "completed"
    start.assert_called_once()
    child.finish.assert_called_once()
    timeout_collector.assert_not_called()


@pytest.mark.parametrize("collector_error", [PermissionError, TimeoutError])
def test_diagnostic_and_report_errors_never_mask_original_timeout(
    load_boundary, monkeypatch, collector_error, capsys
):
    args, replay, _ = load_boundary
    monkeypatch.setattr(
        performance_load_gate, "_wait_for_transaction_processing", lambda **kwargs: None
    )
    monkeypatch.setattr(
        performance_load_gate,
        "collect_load_completion_diagnostics",
        MagicMock(side_effect=collector_error("private details")),
    )
    monkeypatch.setattr(
        performance_load_gate,
        "_write_report",
        MagicMock(side_effect=OSError("publication unavailable")),
    )
    with pytest.raises(
        TimeoutError, match="Replay source transactions did not complete before replay"
    ):
        performance_load_gate.main(args)
    assert "Load report unavailable: OSError" in capsys.readouterr().err
    replay.assert_not_called()


def test_report_publication_failure_makes_success_nonzero(load_boundary, monkeypatch):
    args, _, _ = load_boundary
    monkeypatch.setattr(
        performance_load_gate, "_wait_for_transaction_processing", lambda **kwargs: 1
    )
    monkeypatch.setattr(
        performance_load_gate,
        "_write_report",
        MagicMock(side_effect=OSError("publication failure")),
    )
    with pytest.raises(OSError, match="publication failure"):
        performance_load_gate.main(args)


def test_partial_ingestion_retains_only_accepted_input_before_original_error(
    load_boundary, monkeypatch
):
    args, _, tmp_path = load_boundary
    accepted = MagicMock(status_code=202)
    accepted.json.return_value = {"job_id": "first-job", "payload": "must not retain"}
    rejected = MagicMock(status_code=503, text="denied")
    monkeypatch.setattr(
        performance_load_gate.requests, "post", MagicMock(side_effect=[accepted, rejected])
    )
    with pytest.raises(RuntimeError, match="status=503"):
        performance_load_gate.main(args)
    report = _retained_report(tmp_path)
    assert report["profiles"] == []
    assert report["overall_passed"] is False
    batches = report["completion_evidence"]["submitted_batches"]["steady_state"]
    assert len(batches) == 1 and batches[0]["submitted_count"] == 40
    assert "payload" not in batches[0]["acknowledgement"]


def test_diagnostic_collection_refuses_unbound_runtime_before_any_io(monkeypatch):
    spawn = MagicMock()
    monkeypatch.setattr(load_completion_diagnostics.multiprocessing, "get_context", spawn)
    result = load_completion_diagnostics.collect_load_completion_diagnostics(
        database_url="secret",
        metrics_url="http://foreign",
        kafka_bootstrap_servers="foreign",
        scope={},
        isolated_runtime=False,
    )
    assert result["status"] == "unavailable"
    spawn.assert_not_called()


def test_collection_budget_terminates_owned_probe_without_waiting_for_io(monkeypatch):
    context = MagicMock()
    receiver, sender = MagicMock(), MagicMock()
    receiver.poll.return_value = False
    context.Pipe.return_value = (receiver, sender)
    process = context.Process.return_value
    process.pid = 123
    process.is_alive.side_effect = [True, False]
    monkeypatch.setattr(
        load_completion_diagnostics.multiprocessing, "get_context", lambda mode: context
    )
    result = load_completion_diagnostics.collect_load_completion_diagnostics(
        database_url="secret",
        metrics_url="http://isolated",
        kafka_bootstrap_servers="isolated",
        scope={"run_id": "run", "submitted_ids": ["private-ID"]},
        isolated_runtime=True,
    )
    assert result == {
        "status": "budget_exhausted",
        "scope": {"run_id": "run"},
        "child_cleanup": {"status": "stopped", "errors": []},
    }
    receiver.poll.assert_called_once_with(6.0)
    process.terminate.assert_called_once()
    process.join.assert_called_once_with(timeout=0.2)
    receiver.recv_bytes.assert_not_called()


def test_probe_worker_distinguishes_failure_missing_and_byte_budget(monkeypatch):
    support = load_completion_diagnostics
    monkeypatch.setattr(
        support, "_load_database_diagnostics", MagicMock(side_effect=PermissionError("secret SQL"))
    )
    sender = MagicMock()
    monkeypatch.setattr(support, "_load_consumer_metrics", lambda url: {"status": "unavailable"})
    monkeypatch.setattr(
        support, "_load_consumer_offsets", lambda *args: {"status": "observed", "partitions": []}
    )
    support._diagnostic_worker(
        sender,
        "secret",
        "url",
        "broker",
        {"run_id": "run"},
    )
    result = json.loads(sender.send_bytes.call_args.args[0])
    assert result["probes"]["database"] == {"status": "unavailable", "reason": "PermissionError"}
    assert result["probes"]["ptp_metrics"]["status"] == "unavailable"
    assert "secret" not in sender.send_bytes.call_args.args[0].decode()
    monkeypatch.setattr(support, "_load_consumer_metrics", lambda url: {"data": "x" * 40000})
    support._diagnostic_worker(sender, "secret", "url", "broker", {"run_id": "run"})
    assert json.loads(sender.send_bytes.call_args.args[0])["status"] == "byte_budget_exhausted"


def test_database_probes_are_exact_scoped_read_only_and_permission_failure_is_honest():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchmany.return_value = [{"transaction_count": 24, "portfolio_aggregate_claims": 9000}]
    cursor.execute.side_effect = [None, PermissionError("denied"), None, None, None, None]
    scope = {
        "submitted_ids": ["TX_exact_1"],
        "ingestion_job_ids": ["job"],
        "portfolio_id": GOVERNED_LOAD_PORTFOLIO_ID,
    }
    result = load_completion_diagnostics._load_database_probes(connection, scope, object)
    assert result["outbox_lifecycle"]["status"] == "unavailable"
    assert result["exact_prefix_counts"]["rows"][0]["transaction_count"] == 24
    connection.rollback.assert_called_once()
    for call in cursor.execute.call_args_list:
        query, params = call.args
        assert query.lstrip().startswith(("SELECT", "WITH"))
        assert not re.search(
            r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE)\b", query, re.I
        )
        assert "payload_excerpt" not in query
        if "AS private_statement" in query:
            assert "left(query,2048) AS private_statement" in query
            assert "private_statement" not in str(result["runtime_db_waits"])
        else:
            assert "query," not in query
        assert params
    exact = cursor.execute.call_args_list[0]
    assert "transaction_id=ANY(%s)" in exact.args[0]
    assert scope["submitted_ids"] in exact.args[1]


def test_missing_acknowledgement_never_becomes_zero_rejects():
    connection = MagicMock()
    scope = {
        "submitted_ids": ["TX_exact_1"],
        "ingestion_job_ids": [],
        "portfolio_id": GOVERNED_LOAD_PORTFOLIO_ID,
    }
    result = load_completion_diagnostics._load_database_probes(connection, scope, object)
    assert result["consumer_rejections"]["status"] == "unavailable"
    assert result["ingestion_lifecycle"]["status"] == "unavailable"


@pytest.mark.parametrize(
    "query",
    [
        None,
        "",
        "x" * 2048,
        "SELECT $$secret$$",
        "SELECT /*secret*/ 1",
        "SELECT 'unclosed",
        "CALL secret()",
    ],
)
def test_statement_structure_refuses_ambiguous_or_missing_sql(query):
    assert load_completion_diagnostics._statement_structure(query)["status"] == "unavailable"


def test_statement_structure_retains_lock_shape_without_sensitive_values():
    result = load_completion_diagnostics._statement_structure(
        "SELECT portfolio_id FROM portfolios WHERE portfolio_id = 'private''account' "
        "AND tenant_id = 123 FOR UPDATE"
    )
    assert result["operation"] == "select"
    assert "from portfolios" in result["structure"]
    assert "for update" in result["structure"]
    assert "private" not in str(result) and "123" not in str(result)
    unknown = load_completion_diagnostics._statement_structure(
        "UPDATE \"secret_table\" SET secret_password = 'secret'"
    )
    assert "secret" not in str(unknown)


def test_wait_rows_export_metadata_and_remove_private_statement():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchmany.return_value = [
        {
            "private_statement": "UPDATE portfolios SET status='secret'",
            "backend_xid": "42",
            "query_id": None,
            "query_age_seconds": 18,
            "blocking_pids": [295],
        }
    ]
    result = load_completion_diagnostics._load_database_probes(
        connection, {"submitted_ids": ["tx"], "ingestion_job_ids": [], "portfolio_id": "p"}, object
    )["runtime_db_waits"]
    row = result["rows"][0]
    assert row["backend_xid"] == "42" and row["query_id"] is None
    assert row["blocking_pids"] == [295] and row["query_age_seconds"] == 18
    assert "private_statement" not in row and "secret" not in str(row)


@pytest.mark.parametrize(
    "query,operation,relation",
    [
        (
            'SELECT "portfolio_id" FROM "portfolios" WHERE portfolio_id=$1::VARCHAR FOR UPDATE',
            "select",
            "portfolios",
        ),
        (
            "UPDATE transactions SET gross_cost=$2::NUMERIC WHERE transaction_id=$10::VARCHAR",
            "update",
            "transactions",
        ),
        (
            "INSERT INTO cashflows (transaction_id,quantity) VALUES ($1::VARCHAR,$2::NUMERIC)",
            "insert",
            "cashflows",
        ),
    ],
)
def test_statement_structure_accepts_native_postgres_parameters(query, operation, relation):
    result = load_completion_diagnostics._statement_structure(query)
    assert result["status"] == "observed" and result["operation"] == operation
    assert relation in result["structure"] and "varchar" in result["structure"]
    assert "$" not in result["structure"] and "10" not in result["structure"]


@pytest.mark.parametrize(
    "query", ["SELECT $tag$secret$tag$", "SELECT $$secret$$", "SELECT $1secret"]
)
def test_statement_structure_does_not_confuse_dollar_quotes_with_parameters(query):
    result = load_completion_diagnostics._statement_structure(query)
    assert result["status"] == "unavailable" and "secret" not in str(result)


@pytest.mark.parametrize(
    "value,status",
    [
        ("0", "observed"),
        ("17", "observed"),
        ("17.0", "observed"),
        ("-1", "invalid"),
        ("1.5", "invalid"),
        ("NaN", "invalid"),
        ("Inf", "invalid"),
        (None, "missing"),
    ],
)
def test_counter_scrape_distinguishes_zero_missing_and_invalid(monkeypatch, value, status):
    response = _MetricsResponse()
    response.text = (
        'lotus_core_transaction_processing_operations_total{stage="transaction",'
        f'outcome="processed"}} {value}\n'
        if value is not None
        else "# no counter sample\n"
    )
    monkeypatch.setattr(
        transaction_processing_load_support.requests, "get", lambda *a, **k: response
    )
    result = transaction_processing_load_support.transaction_processing_operation_observation(
        transaction_processing_base_url="http://isolated", stage="transaction", outcome="processed"
    )
    assert result["status"] == status and result["scraped_at"]
    assert result["count"] == (int(float(value)) if status == "observed" else None)
    if status != "observed":
        with pytest.raises(RuntimeError, match="not observed"):
            transaction_processing_load_support.transaction_processing_operation_count(
                transaction_processing_base_url="http://isolated",
                stage="transaction",
                outcome="processed",
            )


@pytest.mark.parametrize("value", [2**60 + 1, True, -1, 1.5, float("nan"), float("inf")])
def test_counter_parser_integer_precision_and_invalid_numeric_types(monkeypatch, value):
    support = transaction_processing_load_support
    response = _MetricsResponse()
    response.text = "synthetic parser sample\n"
    monkeypatch.setattr(support.requests, "get", lambda *a, **k: response)
    sample = SimpleNamespace(
        name="lotus_core_transaction_processing_operations_total",
        labels={"stage": "transaction", "outcome": "processed"},
        value=value,
    )
    monkeypatch.setattr(
        support, "text_string_to_metric_families", lambda text: [SimpleNamespace(samples=[sample])]
    )
    result = support.transaction_processing_operation_observation(
        transaction_processing_base_url="http://isolated", stage="transaction", outcome="processed"
    )
    if type(value) is int and value >= 0:
        assert result["status"] == "observed" and result["count"] == value
        assert result["count"] != int(float(value))
    else:
        assert result["status"] == "invalid" and result["count"] is None


@pytest.mark.parametrize(
    "raw,reason",
    [
        (
            'lotus_core_transaction_processing_operations_total{stage="transaction",'
            'outcome="processed",secret="PRIVATE"} 2\n',
            "counter_labels",
        ),
        (
            (
                'lotus_core_transaction_processing_operations_total{stage="transaction",'
                'outcome="processed"} 2\n'
            )
            * 2,
            "ambiguous",
        ),
        ("x" * (1024 * 1024 + 1), "byte_budget"),
        ("not prometheus {{", "ValueError"),
    ],
    ids=["private-label", "duplicate", "oversize", "malformed"],
)
def test_counter_scrape_refuses_ambiguous_private_oversize_or_malformed(monkeypatch, raw, reason):
    response = _MetricsResponse()
    response.text = raw
    monkeypatch.setattr(
        transaction_processing_load_support.requests, "get", lambda *a, **k: response
    )
    result = transaction_processing_load_support.transaction_processing_operation_observation(
        transaction_processing_base_url="http://isolated", stage="transaction", outcome="processed"
    )
    assert result["status"] != "observed" and result["reason"] == reason
    assert "PRIVATE" not in str(result) and result["count"] is None


@pytest.mark.parametrize(
    "baseline,counts,passed",
    [
        (10, [11, 14, 14], True),
        (10, [0, 14, 14], False),
        (None, [14, 14, 14], False),
        (10, [None, None, None], False),
    ],
)
def test_counter_polling_keeps_reset_missing_failure_and_original_deadline(
    monkeypatch, baseline, counts, passed
):
    support = transaction_processing_load_support

    def observation(count):
        return {
            "status": "observed" if count is not None else "missing",
            "count": count,
            "labels": {"stage": "transaction", "outcome": "processed"},
            "producer_birth": 123,
        }

    readings = iter(counts)
    clock = iter([0, 0, 1, 2, 3, 4, 5])
    monkeypatch.setattr(support.time, "time", lambda: next(clock))
    monkeypatch.setattr(support.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        support,
        "transaction_processing_operation_observation",
        lambda **k: observation(next(readings)),
    )
    retained = []
    result = support.wait_for_transaction_processing_operation_count(
        transaction_processing_base_url="http://isolated",
        stage="transaction",
        outcome="processed",
        expected_minimum=14,
        timeout_seconds=3,
        baseline=observation(baseline),
        on_observation=retained.append,
    )
    assert (result is not None) is passed
    assert retained[-1]["count"] == counts[len(retained) - 1]
    if baseline is None or counts[0] == 0:
        assert retained[-1]["continuity"] == "reset_or_missing_baseline"


@pytest.mark.parametrize(
    "accepted,status",
    [
        (1, "observed_count_only"),
        (True, "refused_or_invalid"),
        (-1, "refused_or_invalid"),
        (3, "refused_or_invalid"),
        ("2", "refused_or_invalid"),
    ],
)
def test_replay_receipts_keep_order_partial_ack_and_refuse_bad_counts(
    monkeypatch, accepted, status
):
    response = SimpleNamespace(
        status_code=202,
        json=lambda: {
            "accepted_count": accepted,
            "job_id": "job-1",
            "private_payload": "PRIVATE",
            "accepted_ids": ["untrusted-other-id"],
        },
    )
    monkeypatch.setattr(performance_load_gate.requests, "post", lambda *a, **k: response)
    receipts = []
    kwargs = dict(
        ingestion_base_url="http://isolated",
        transaction_ids=["TX-2", "TX-1"],
        bursts=2,
        burst_size=2,
        on_acknowledgement=receipts.append,
    )
    if status == "refused_or_invalid":
        with pytest.raises(RuntimeError, match="invalid accepted_count"):
            performance_load_gate._trigger_replay_storm(**kwargs)
    else:
        assert performance_load_gate._trigger_replay_storm(**kwargs) == 2
        assert [r["submitted_ids"] for r in receipts] == [["TX-2", "TX-1"]] * 2
    assert receipts[0]["acceptance_status"] == status
    assert receipts[0]["accepted_ids"] == "MISSING"
    assert receipts[0]["durable_completion_receipts"] == "MISSING"
    assert receipts[0]["acknowledgement"]["job_id"] == "job-1"
    assert "PRIVATE" not in str(receipts) and "untrusted-other-id" not in str(receipts)


def test_replay_transport_failure_retains_submission_without_private_error(monkeypatch):
    monkeypatch.setattr(
        performance_load_gate.requests,
        "post",
        MagicMock(side_effect=performance_load_gate.requests.ConnectionError("PRIVATE")),
    )
    receipts = []
    with pytest.raises(RuntimeError, match="transport failed") as error:
        performance_load_gate._trigger_replay_storm(
            ingestion_base_url="http://isolated",
            transaction_ids=["TX-1"],
            bursts=1,
            burst_size=1,
            on_acknowledgement=receipts.append,
        )
    assert receipts[0]["submitted_ids"] == ["TX-1"]
    assert receipts[0]["acceptance_status"] == "transport_failure"
    assert "PRIVATE" not in str(receipts) + str(error.value)


def test_main_replay_timeout_collects_once_preserves_failure_and_counter_record(
    load_boundary, monkeypatch
):
    args, replay, tmp_path = load_boundary
    monkeypatch.setattr(performance_load_gate, "_wait_for_transaction_processing", lambda **k: 1)

    def wait(**kwargs):
        assert kwargs["expected_minimum"] == 360 and kwargs["timeout_seconds"] == 240
        kwargs["on_observation"]({"status": "missing", "count": None})
        return None

    monkeypatch.setattr(performance_load_gate, "_wait_for_repair_replay_completion", wait)
    collector = MagicMock(return_value={"status": "budget_exhausted"})
    monkeypatch.setattr(performance_load_gate, "collect_load_completion_diagnostics", collector)
    assert performance_load_gate.main(args) == 1
    collector.assert_called_once()
    payload = _retained_report(tmp_path)
    assert payload["overall_passed"] is False
    record = payload["completion_evidence"]["replay_completion"]
    assert record["baseline"]["count"] == 0 and record["target"] == 360
    assert record["final"] == {"status": "missing", "count": None}
    assert record["exact_await"] == "MISSING"
    assert record["diagnostics"]["claims_scope"] == "preexisting_rows_not_replay_receipts"


def test_managed_worker_observation_is_exact_birth_qualified_and_not_worker_pid(monkeypatch):
    support = load_completion_diagnostics
    identifier = "a" * 64
    service = "portfolio_transaction_processing_service"
    run = MagicMock(
        side_effect=[
            SimpleNamespace(stdout=identifier),
            SimpleNamespace(
                stdout=json.dumps(
                    [
                        identifier,
                        "2026-10-07T01:00:00Z",
                        "2026-10-07T01:01:00Z",
                        123,
                        "owned-load",
                        service,
                        [{"HostPort": "26090"}],
                    ]
                )
            ),
        ]
    )
    monkeypatch.setattr(support.subprocess, "run", run)
    result = support._load_managed_worker_identity(
        {"runtime": "owned-load", "compose_file": "compose.yml", "metrics_port": 26090}
    )
    assert result["status"] == "observed" and result["container_init_pid"] == 123
    assert result["container_id"] == identifier and result["started_at"] == "2026-10-07T01:01:00Z"
    assert result["worker_pid"] == result["exact_await"] == "MISSING"
    assert run.call_args_list[0].args[0] == [
        "docker",
        "ps",
        "--no-trunc",
        "--quiet",
        "--filter",
        "label=com.docker.compose.project=owned-load",
        "--filter",
        f"label=com.docker.compose.service={service}",
    ]
    assert all(
        call.kwargs["timeout"] == 0.5 and call.kwargs["check"] for call in run.call_args_list
    )
    assert ".Config.Env" not in run.call_args.args[0][3]


@pytest.mark.parametrize("timeout_command", ["ps", "inspect"])
def test_plain_docker_identity_timeout_reaps_owned_direct_process(monkeypatch, timeout_command):
    """Use real captured pipes/timeout/cleanup, without invoking Docker or a plugin tree."""
    native_run, native_popen = subprocess.run, subprocess.Popen
    owned = []
    commands = []

    def track_process(*args, **kwargs):
        child = native_popen(*args, **kwargs)
        owned.append(child)
        return child

    def run_direct_control(command, **kwargs):
        commands.append(command)
        assert command[0] == "docker" and command[1] in {"ps", "inspect"}
        assert "compose" not in command and not kwargs.get("shell", False)
        if command[1] != timeout_command:
            return SimpleNamespace(stdout="a" * 64)
        # A single executable owns these pipes: no shell or Compose plugin intermediary.
        return native_run([sys.executable, "-c", "import time; time.sleep(5)"], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", track_process)
    monkeypatch.setattr(subprocess, "run", run_direct_control)
    monkeypatch.setattr(load_completion_diagnostics, "DIAGNOSTIC_IO_SECONDS", 0.1)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        load_completion_diagnostics._load_managed_worker_identity(
            {"runtime": "owned-load", "compose_file": "compose.yml", "metrics_port": 26090}
        )
    assert time.monotonic() - started < 2
    assert len(owned) == 1 and owned[0].poll() is not None
    assert len(commands) == (1 if timeout_command == "ps" else 2)


@pytest.mark.parametrize("identifiers", ["", "a" * 12, "a" * 64 + "\n" + "b" * 64])
def test_plain_docker_lookup_refuses_missing_truncated_or_multiple_containers(
    monkeypatch, identifiers
):
    run = MagicMock(return_value=SimpleNamespace(stdout=identifiers))
    monkeypatch.setattr(subprocess, "run", run)
    result = load_completion_diagnostics._load_managed_worker_identity(
        {"runtime": "owned-load", "compose_file": "compose.yml", "metrics_port": 26090}
    )
    assert result == {"status": "missing", "reason": "container_identity_ambiguous"}
    assert run.call_count == 1


@pytest.mark.parametrize(
    "returned",
    [
        [],
        ["other", "created", "started", 123, "foreign", "other"],
        [
            "a" * 64,
            "created",
            "started",
            0,
            "owned-load",
            "portfolio_transaction_processing_service",
            [{"HostPort": "26090"}],
        ],
        [
            "a" * 64,
            "created",
            "started",
            123,
            "owned-load",
            "portfolio_transaction_processing_service",
            [{"HostPort": "8090"}],
        ],
    ],
)
def test_managed_worker_refuses_foreign_missing_or_stopped_identity(monkeypatch, returned):
    run = MagicMock(
        side_effect=[SimpleNamespace(stdout="a" * 64), SimpleNamespace(stdout=json.dumps(returned))]
    )
    monkeypatch.setattr(load_completion_diagnostics.subprocess, "run", run)
    result = load_completion_diagnostics._load_managed_worker_identity(
        {"runtime": "owned-load", "compose_file": "compose.yml", "metrics_port": 26090}
    )
    assert result["status"] != "observed"
    assert "foreign" not in str(result)


def test_lock_probe_qualifies_pid_birth_and_keeps_null_relation_noncausal():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchmany.return_value = [
        {
            "pid": 123,
            "backend_start": "birth",
            "database_oid": 9,
            "relation_oid": None,
            "locktype": "transactionid",
            "granted": False,
        }
    ]
    result = load_completion_diagnostics._load_database_probes(
        connection,
        {"submitted_ids": ["TX-1"], "ingestion_job_ids": [], "portfolio_id": "p"},
        object,
    )
    lock = result["runtime_db_locks"]["rows"][0]
    assert lock["relation_oid"] is None and lock["backend_start"] == "birth"
    wait = result["runtime_db_waits"]["rows"][0]
    assert wait["exact_await"] == "MISSING"
    queries = [c.args[0] for c in cursor.execute.call_args_list]
    assert any("JOIN activity a ON a.pid=l.pid" in q and "a.backend_start" in q for q in queries)


@pytest.mark.parametrize("birth,passed", [(123, True), (124, False), ("MISSING", False)])
def test_same_counter_labels_and_increasing_counts_do_not_hide_worker_replacement(
    monkeypatch, birth, passed
):
    support = transaction_processing_load_support
    clock = iter([0, 0, 1, 2, 3, 4])
    monkeypatch.setattr(support.time, "time", lambda: next(clock))
    monkeypatch.setattr(support.time, "sleep", lambda seconds: None)
    baseline = {
        "status": "observed",
        "count": 10,
        "producer_birth": 123,
        "labels": {"stage": "transaction", "outcome": "processed"},
    }
    monkeypatch.setattr(
        support,
        "transaction_processing_operation_observation",
        lambda **k: {**baseline, "count": 99, "producer_birth": birth},
    )
    observations = []
    result = support.wait_for_transaction_processing_operation_count(
        transaction_processing_base_url="http://isolated",
        stage="transaction",
        outcome="processed",
        expected_minimum=14,
        timeout_seconds=3,
        baseline=baseline,
        on_observation=observations.append,
    )
    assert (result is not None) is passed
    assert observations[-1]["continuity"] == ("observed" if passed else "reset_or_missing_baseline")


def test_completion_scrape_separate_input_budget_and_same_exposition_process_birth(monkeypatch):
    response = _MetricsResponse()
    response.text = (
        "# bounded histogram-family padding\n" * 3000
        + "process_start_time_seconds 123\n"
        + 'lotus_core_transaction_processing_operations_total{stage="transaction",'
        'outcome="processed"} 17\n'
    )
    assert len(response.text) > 32768
    monkeypatch.setattr(
        transaction_processing_load_support.requests, "get", lambda *a, **k: response
    )
    result = transaction_processing_load_support.transaction_processing_operation_observation(
        transaction_processing_base_url="http://isolated", stage="transaction", outcome="processed"
    )
    assert (
        result["status"] == "observed" and result["producer_birth"] == 123 and result["count"] == 17
    )


@pytest.mark.parametrize("birth", ["MISSING", None])
def test_missing_baseline_producer_identity_cannot_qualify_later_counter(monkeypatch, birth):
    support = transaction_processing_load_support
    baseline = {"status": "observed", "count": 10, "labels": {}, "producer_birth": birth}
    current = {**baseline, "count": 99, "producer_birth": 123}
    clock = iter([0, 0, 1, 2, 3, 4])
    monkeypatch.setattr(support.time, "time", lambda: next(clock))
    monkeypatch.setattr(support.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        support, "transaction_processing_operation_observation", lambda **k: current
    )
    assert (
        support.wait_for_transaction_processing_operation_count(
            transaction_processing_base_url="http://isolated",
            stage="transaction",
            outcome="processed",
            expected_minimum=14,
            timeout_seconds=3,
            baseline=baseline,
        )
        is None
    )


def test_counter_recreation_with_same_process_and_high_value_refuses_completion(monkeypatch):
    support = transaction_processing_load_support
    baseline = {
        "status": "observed",
        "count": 10,
        "labels": {},
        "producer_birth": 123,
        "counter_created_at": 124,
    }
    current = {**baseline, "count": 99, "counter_created_at": 125}
    clock = iter([0, 0, 1, 2, 3, 4])
    monkeypatch.setattr(support.time, "time", lambda: next(clock))
    monkeypatch.setattr(support.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        support, "transaction_processing_operation_observation", lambda **k: current
    )
    assert (
        support.wait_for_transaction_processing_operation_count(
            transaction_processing_base_url="http://isolated",
            stage="transaction",
            outcome="processed",
            expected_minimum=14,
            timeout_seconds=3,
            baseline=baseline,
        )
        is None
    )


def test_replay_diagnostic_once_even_if_collection_refuses_or_raises(load_boundary, monkeypatch):
    args, _, _ = load_boundary
    collector = MagicMock(side_effect=PermissionError("PRIVATE"))
    monkeypatch.setattr(performance_load_gate, "collect_load_completion_diagnostics", collector)
    report = performance_load_gate._LoadEvidenceReport(args, "run", MagicMock(), None)
    report.stage = "replay_storm"
    report.replay_timeout()
    report.replay_timeout()
    collector.assert_called_once()
    assert report.replay_completion["diagnostics"]["reason"] == "PermissionError"
    assert "PRIVATE" not in str(report.replay_completion)


def test_identity_probe_missing_scope_does_not_invoke_docker(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(load_completion_diagnostics.subprocess, "run", run)
    assert load_completion_diagnostics._load_managed_worker_identity({})["status"] == "missing"
    run.assert_not_called()


def _diagnostic_test_child(sender, database_url, metrics_url, broker, scope, *probes):
    """Real isolated subprocess test: no DB, Kafka, HTTP, Docker or product execution."""
    if scope.get("block"):
        time.sleep(10)
    else:
        sender.send_bytes(json.dumps({"status": "observed", "probe": "test_only"}).encode())
    sender.close()


@pytest.mark.parametrize("block", [False, True])
def test_real_owned_probe_process_completion_and_timeout_are_reaped(monkeypatch, block):
    support = load_completion_diagnostics
    native = multiprocessing.get_context("spawn")
    children = []

    class Context:
        Pipe = staticmethod(native.Pipe)

        @staticmethod
        def Process(*, target, args, daemon):
            child = native.Process(target=_diagnostic_test_child, args=args, daemon=daemon)
            children.append(child)
            return child

    monkeypatch.setattr(support.multiprocessing, "get_context", lambda mode: Context())
    monkeypatch.setattr(support, "DIAGNOSTIC_BUDGET_SECONDS", 2.0 if not block else 0.1)
    result = support.collect_load_completion_diagnostics(
        database_url="unused",
        metrics_url="unused",
        kafka_bootstrap_servers="unused",
        scope={"block": block},
        isolated_runtime=True,
    )
    assert result["status"] == ("budget_exhausted" if block else "observed")
    assert result["child_cleanup"]["status"] == "stopped"
    assert all(child._closed for child in children)


def test_process_start_and_cleanup_failures_are_data_not_replacement_exceptions(monkeypatch):
    context = MagicMock()
    receiver, sender = MagicMock(), MagicMock()
    context.Pipe.return_value = (receiver, sender)
    process = context.Process.return_value
    process.start.side_effect = OSError("start failure with secret")
    process.pid = None
    process.close.side_effect = OSError("close failure")
    monkeypatch.setattr(
        load_completion_diagnostics.multiprocessing, "get_context", lambda mode: context
    )
    result = load_completion_diagnostics.collect_load_completion_diagnostics(
        database_url="secret",
        metrics_url="url",
        kafka_bootstrap_servers="broker",
        scope={},
        isolated_runtime=True,
    )
    assert result["status"] == "unavailable" and result["reason"] == "OSError"
    assert result["child_cleanup"] == {"status": "not_started", "errors": ["OSError"]}
    assert "secret" not in json.dumps(result)


def test_cleanup_terminate_error_uses_kill_and_confirms_absence():
    process = MagicMock(pid=123)
    process.is_alive.side_effect = [True, True, False]
    process.terminate.side_effect = OSError("denied")
    result = load_completion_diagnostics._stop_diagnostic_process(process)
    assert result == {"status": "stopped", "errors": ["OSError"]}
    process.kill.assert_called_once()


def test_cleanup_guard_reports_unconfirmed_stop_honestly():
    process = MagicMock(pid=123)
    process.is_alive.return_value = True
    process.terminate.side_effect = OSError("denied")
    process.kill.side_effect = OSError("denied")
    assert load_completion_diagnostics._stop_diagnostic_process(process)["status"] == "unconfirmed"
    process.close.assert_not_called()


def test_database_connection_has_native_read_only_short_limits_and_owner_guard(monkeypatch):
    from portfolio_common import db
    from sqlalchemy.pool import NullPool

    engine = MagicMock()
    connection = engine.raw_connection.return_value
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"tenant_id": "foreign"}
    create = MagicMock(return_value=engine)
    monkeypatch.setattr(db, "create_engine", create)
    monkeypatch.setenv("LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS", "3000")
    result = load_completion_diagnostics._load_database_diagnostics(
        "postgresql://operator:nondefault-secret@isolated/db?sslmode=require",
        {"portfolio_id": GOVERNED_LOAD_PORTFOLIO_ID},
    )
    assert result["status"] == "unavailable"
    settings = create.call_args.kwargs
    assert settings["poolclass"] is NullPool
    assert settings["connect_args"]["connect_timeout"] == 2
    assert settings["connect_args"]["application_name"] == "performance-load-gate"
    assert "statement_timeout=500" in settings["connect_args"]["options"]
    assert "sslmode=require" in create.call_args.args[0]
    connection.set_session.assert_called_once_with(readonly=True, autocommit=True)
    assert cursor.execute.call_args_list[0].args == ("SET lock_timeout = '100ms'",)
    assert cursor.execute.call_count == 2
    connection.close.assert_called_once()
    engine.dispose.assert_called_once()
    assert os.environ["LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS"] == "60"
    assert os.environ["LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS"] == "3000"


@pytest.mark.parametrize("stage", ["connection", "read_only", "owner", "probe", "close"])
def test_diagnostic_database_failure_disposes_engine_and_closes_connection(monkeypatch, stage):
    engine = MagicMock()
    connection = engine.raw_connection.return_value
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"tenant_id": load_completion_diagnostics.LOAD_TENANT_ID}
    monkeypatch.setattr(
        load_completion_diagnostics, "_diagnostic_database_engine", lambda url: engine
    )
    if stage == "connection":
        engine.raw_connection.side_effect = PermissionError("refused")
    elif stage == "read_only":
        connection.set_session.side_effect = PermissionError("refused")
    elif stage == "owner":
        cursor.execute.side_effect = PermissionError("refused")
    elif stage == "probe":
        monkeypatch.setattr(
            load_completion_diagnostics,
            "_load_database_probes",
            MagicMock(side_effect=PermissionError),
        )
    else:
        connection.close.side_effect = PermissionError("refused")
    with pytest.raises(PermissionError):
        load_completion_diagnostics._load_database_diagnostics(
            "unused",
            {
                "portfolio_id": GOVERNED_LOAD_PORTFOLIO_ID,
                "submitted_ids": [],
                "ingestion_job_ids": [],
            },
        )
    engine.dispose.assert_called_once()
    if stage != "connection":
        connection.close.assert_called_once()


def test_diagnostic_database_security_refusal_preserves_parent_profile(monkeypatch):
    from portfolio_common import db
    from portfolio_common.runtime_settings import RuntimeConfigurationError

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS", "60")
    create = MagicMock()
    monkeypatch.setattr(db, "create_engine", create)
    with pytest.raises(RuntimeConfigurationError):
        load_completion_diagnostics._diagnostic_database_engine("postgresql://user@isolated/db")
    create.assert_not_called()
    assert os.environ["LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS"] == "60"


def test_diagnostic_database_inherited_invalid_profile_is_not_weakened(monkeypatch):
    from portfolio_common import db
    from portfolio_common.database_runtime_profile import DatabaseRuntimeProfileError

    monkeypatch.setenv("LOTUS_CORE_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS", "1")
    create = MagicMock()
    monkeypatch.setattr(db, "create_engine", create)
    with pytest.raises(DatabaseRuntimeProfileError):
        load_completion_diagnostics._diagnostic_database_engine(
            "postgresql://operator:nondefault-secret@isolated/db"
        )
    create.assert_not_called()
    assert os.environ["LOTUS_CORE_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS"] == "1"


@pytest.mark.parametrize("missing,oversized", [(False, False), (True, False), (False, True)])
def test_consumer_metrics_missing_and_byte_limits_never_become_zero(
    monkeypatch, missing, oversized
):
    support = load_completion_diagnostics
    response = MagicMock()
    body = (
        b"unrelated_metric 1\n"
        if missing
        else b'kafka_consumer_in_flight_messages{service="TXNPROC",'
        b'topic="transactions.persisted",group_id="portfolio_transaction_processing_group"} 12\n'
    )
    if oversized:
        body += b"x" * support.DIAGNOSTIC_METRICS_INPUT_MAX_BYTES
    response.iter_content.return_value = [body]
    response.__enter__.return_value = response
    get = MagicMock(return_value=response)
    monkeypatch.setattr(support.requests, "get", get)
    result = load_completion_diagnostics._load_consumer_metrics("http://isolated/metrics")
    assert result["status"] == (
        "byte_budget_exhausted" if oversized else "unavailable" if missing else "observed"
    )
    if not missing and not oversized:
        assert result["samples"][0]["value"] == 12
        assert result["scope"] == "runtime_aggregate_not_prefix"
    assert get.call_args.kwargs["timeout"] == 0.5


@pytest.mark.parametrize("protocol", ["SSL", "SASL_SSL"])
def test_native_kafka_offset_reads_do_not_join_store_or_commit(monkeypatch, protocol):
    import confluent_kafka

    consumer = MagicMock()
    consumer.list_topics.return_value.topics = {
        name: SimpleNamespace(error=None, partitions={0: object()})
        for name in (
            "transactions.raw.received",
            "transactions.persisted",
            "transactions.reprocessing.requested",
        )
    }
    consumer.committed.return_value = [SimpleNamespace(offset=5, error=None)]
    consumer.get_watermark_offsets.return_value = (0, 12)
    factory = MagicMock(return_value=consumer)
    monkeypatch.setattr(confluent_kafka, "Consumer", factory)
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", protocol)
    monkeypatch.setenv("KAFKA_SSL_CA_LOCATION", "/deployment/trust.pem")
    monkeypatch.setenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
    monkeypatch.setenv("KAFKA_SASL_USERNAME", "diagnostic-operator")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD", "inherited-secret")
    result = load_completion_diagnostics._load_consumer_offsets("isolated", time.monotonic() + 10)
    assert [row["committed"] for row in result["partitions"]] == [5, 5, 5]
    assert [row["end"] for row in result["partitions"]] == [12, 12, 12]
    assert factory.call_count == consumer.close.call_count == 3
    for call in factory.call_args_list:
        assert call.args[0]["enable.auto.commit"] is False
        assert call.args[0]["enable.auto.offset.store"] is False
        assert call.args[0]["allow.auto.create.topics"] is False
        assert call.args[0]["security.protocol"] == protocol
        assert call.args[0]["ssl.ca.location"] == "/deployment/trust.pem"
        if protocol == "SASL_SSL":
            assert call.args[0]["sasl.mechanism"] == "SCRAM-SHA-512"
            assert call.args[0]["sasl.username"] == "diagnostic-operator"
            assert call.args[0]["sasl.password"] == "inherited-secret"
    for method in (consumer.subscribe, consumer.assign, consumer.commit, consumer.store_offsets):
        method.assert_not_called()


def _diagnostic_metrics_response(monkeypatch, body):
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [
        body[index : index + 4096] for index in range(0, len(body), 4096)
    ]
    monkeypatch.setattr(
        load_completion_diagnostics.requests, "get", MagicMock(return_value=response)
    )
    return response


@pytest.mark.parametrize("value", ["1", "NaN", "+Inf", "-Inf"])
def test_diagnostic_metric_values_are_finite_strict_json_or_unavailable(monkeypatch, value):
    body = (
        'kafka_consumer_in_flight_messages{service="TXNPROC",topic="transactions.persisted",'
        'group_id="portfolio_transaction_processing_group"} ' + value + "\n"
    ).encode()
    _diagnostic_metrics_response(monkeypatch, body)
    result = load_completion_diagnostics._load_consumer_metrics("http://isolated/metrics")
    json.dumps(result, allow_nan=False)
    if value == "1":
        assert result["status"] == "observed"
        assert result["samples"][0]["value"] == 1
    else:
        assert result == {"status": "unavailable", "reason": "nonfinite_metric_value"}


def test_diagnostic_metrics_larger_than_output_budget_still_projects_bounded_samples(monkeypatch):
    support = load_completion_diagnostics
    body = b"# unrelated exposition padding\n" * 2500
    body += (
        b'kafka_consumer_in_flight_messages{service="TXNPROC",topic="transactions.persisted",'
        b'group_id="portfolio_transaction_processing_group"} 3\n'
    )
    assert support.DIAGNOSTIC_MAX_BYTES < len(body) < support.DIAGNOSTIC_METRICS_INPUT_MAX_BYTES
    response = _diagnostic_metrics_response(monkeypatch, body)
    result = support._load_consumer_metrics("http://isolated/metrics")
    assert result["status"] == "observed" and result["samples"][0]["value"] == 3
    assert len(json.dumps(result).encode()) < support.DIAGNOSTIC_MAX_BYTES == 32768
    response.__exit__.assert_called_once()


@pytest.mark.parametrize("body", [b"\xff", b'metric{bad="unterminated} 1\n'])
def test_diagnostic_malformed_metrics_refuse_without_exporting_input(monkeypatch, body):
    _diagnostic_metrics_response(monkeypatch, body)
    result = load_completion_diagnostics._load_consumer_metrics("http://isolated/metrics")
    assert result == {"status": "unavailable", "reason": "malformed_metrics"}


@pytest.mark.parametrize(
    "private_label",
    [
        'tenant_id="private-client"',
        'topic="private-client"',
        'group_id="private-client"',
        'reason="private-client"',
    ],
)
def test_diagnostic_metrics_refuse_private_label_scope_and_values(monkeypatch, private_label):
    body = (
        'kafka_consumer_in_flight_messages{service="portfolio-transaction-processing",'
        + private_label
        + "} 9\n"
    ).encode()
    _diagnostic_metrics_response(monkeypatch, body)
    result = load_completion_diagnostics._load_consumer_metrics("http://isolated/metrics")
    assert result["status"] == "unavailable" and "private-client" not in json.dumps(result)
    assert "samples" not in result


def test_diagnostic_metrics_without_selected_samples_are_unavailable_not_measured_zero(monkeypatch):
    _diagnostic_metrics_response(monkeypatch, b"unrelated_metric 0\n")
    result = load_completion_diagnostics._load_consumer_metrics("http://isolated/metrics")
    assert result["status"] == "unavailable"
    assert result["reason"] == "no_matching_consumer_metric_samples"
    assert "samples" not in result
    assert result["recognized_samples"] == 0


def test_diagnostic_metrics_row_truncation_is_explicit(monkeypatch):
    body = "".join(
        'kafka_consumer_partition_lag_messages{service="TXNPROC",topic="transactions.persisted",group_id="portfolio_transaction_processing_group",partition="'
        + str(i)
        + '"} 1\n'
        for i in range(25)
    ).encode()
    _diagnostic_metrics_response(monkeypatch, body)
    result = load_completion_diagnostics._load_consumer_metrics("http://isolated/metrics")
    assert result["truncated"] and len(result["samples"]) == 20


def _diagnostic_offset_clients(monkeypatch, partition_count):
    import confluent_kafka

    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SSL")
    monkeypatch.setenv("KAFKA_SSL_CA_LOCATION", "/deployment/trust.pem")
    groups = [
        "persistence_group_transactions",
        "portfolio_transaction_processing_group",
        "portfolio_transaction_replay_request_group",
    ]
    topics = [
        "transactions.raw.received",
        "transactions.persisted",
        "transactions.reprocessing.requested",
    ]
    clients = {}
    for group, topic in zip(groups, topics, strict=True):
        client = MagicMock()
        client.list_topics.return_value.topics = {
            topic: SimpleNamespace(error=None, partitions=dict.fromkeys(range(partition_count)))
        }
        client.committed.return_value = [SimpleNamespace(offset=5, error=None)]
        client.get_watermark_offsets.return_value = (0, 12)
        clients[group] = client
    factory = MagicMock(side_effect=lambda config: clients[config["group.id"]])
    monkeypatch.setattr(confluent_kafka, "Consumer", factory)
    return clients, factory


def test_diagnostic_three_groups_share_twenty_rows_fairly_without_joining(monkeypatch):
    clients, factory = _diagnostic_offset_clients(monkeypatch, 12)
    result = load_completion_diagnostics._load_consumer_offsets("isolated", time.monotonic() + 10)
    assert result["status"] == "observed" and result["truncated"]
    rows = result["partitions"]
    assert len(rows) == 20
    assert [sum(row["group_id"] == group for row in rows) for group in clients] == [7, 7, 6]
    assert len({row["group_id"] for row in rows[:3]}) == 3
    assert factory.call_count == 3
    for client in clients.values():
        client.close.assert_called_once()
        for operation in (client.subscribe, client.assign, client.commit, client.store_offsets):
            operation.assert_not_called()


@pytest.mark.parametrize("failure", ["metadata", "offset", "construction"])
def test_diagnostic_offset_failure_keeps_other_group_evidence_and_closes_owners(
    monkeypatch, failure
):
    clients, factory = _diagnostic_offset_clients(monkeypatch, 1)
    replay = clients["portfolio_transaction_replay_request_group"]
    if failure == "metadata":
        replay.list_topics.side_effect = RuntimeError("private-client")
    elif failure == "offset":
        replay.committed.side_effect = RuntimeError("private-client")
    else:
        factory.side_effect = [
            clients["persistence_group_transactions"],
            RuntimeError("private-client"),
        ]
        with pytest.raises(RuntimeError):
            load_completion_diagnostics._load_consumer_offsets("isolated", time.monotonic() + 10)
        clients["persistence_group_transactions"].close.assert_called_once()
        replay.close.assert_not_called()
        return
    result = load_completion_diagnostics._load_consumer_offsets("isolated", time.monotonic() + 10)
    assert result["status"] == "partial" and len(result["partitions"]) == 2
    assert result["groups"][2]["status"] == "unavailable"
    assert "private-client" not in json.dumps(result)
    for client in clients.values():
        client.close.assert_called_once()


def test_diagnostic_offset_deadline_closes_all_clients_without_claiming_zero(monkeypatch):
    clients, _ = _diagnostic_offset_clients(monkeypatch, 1)
    monkeypatch.setattr(
        load_completion_diagnostics.time, "monotonic", MagicMock(side_effect=[0, 0, 0, 0, 9])
    )
    result = load_completion_diagnostics._load_consumer_offsets("isolated", 6)
    assert result["status"] == "budget_exhausted" and result["partitions"] == []
    for client in clients.values():
        client.close.assert_called_once()


@pytest.mark.parametrize("stale", [False, True])
def test_diagnostic_lock_projection_qualifies_sql_ordered_rows_and_reports_truncation(
    monkeypatch, stale
):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    waits = [
        {"pid": 100, "backend_start": "wait-birth"},
        {"pid": 200, "backend_start": "head-birth"},
    ]
    edge = {
        "waiter_pid": 100,
        "waiter_backend_start": "wait-birth",
        "blocker_pid": 200,
        "blocker_backend_start": "old-birth" if stale else "head-birth",
    }
    locks = [
        {"pid": i, "backend_start": "noise", "blocking_role": "runtime_sample", "total_rows": 32}
        for i in range(1, 31)
    ]
    locks += [
        {
            **edge,
            "pid": 200,
            "backend_start": "head-birth",
            "blocking_role": "blocker_head",
            "granted": True,
            "relation_oid": None,
            "total_rows": 32,
        },
        {
            **edge,
            "pid": 100,
            "backend_start": "wait-birth",
            "blocking_role": "waiting_edge",
            "granted": False,
            "total_rows": 32,
        },
    ]
    # Model the driver cap and SQL ordering, not Python recovery of unseen rows.
    # Actual priority over lower-PID noise requires the separate native PG proof.
    sql_ordered = locks[-2:] + locks[:19]
    cursor.fetchmany.side_effect = [[], [], waits, sql_ordered]
    assert len(sql_ordered) == load_completion_diagnostics.DIAGNOSTIC_MAX_ROWS + 1
    result = load_completion_diagnostics._load_database_probes(
        connection, {"submitted_ids": [], "ingestion_job_ids": [], "portfolio_id": "p"}, object
    )
    projected = result["runtime_db_locks"]
    assert projected["truncated"] and len(projected["rows"]) == 20
    if not stale:
        assert [row["blocking_role"] for row in projected["rows"][:2]] == [
            "blocker_head",
            "waiting_edge",
        ]
        assert all(row["edge_identity_status"] == "observed" for row in projected["rows"][:2])
        assert projected["rows"][0]["relation_oid"] is None
    else:
        assert not any(row.get("edge_identity_status") == "observed" for row in projected["rows"])
    query = cursor.execute.call_args_list[-1].args[0]
    assert (
        "AS MATERIALIZED" in query
        and "waiter_backend_start" in query
        and "blocker_backend_start" in query
    )
    assert "IS NOT DISTINCT FROM" in query and "ORDER BY (edge.blocker_pid IS NULL)" in query
    assert "LIMIT 21" in query and cursor.fetchmany.call_args.args == (21,)


@pytest.mark.parametrize("protocol", ["SSL", "PLAINTEXT", "INVALID"])
def test_kafka_security_refusal_is_unavailable_without_client_construction(monkeypatch, protocol):
    import confluent_kafka

    factory = MagicMock()
    monkeypatch.setattr(confluent_kafka, "Consumer", factory)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", protocol)
    monkeypatch.delenv("KAFKA_SSL_CA_LOCATION", raising=False)
    monkeypatch.setattr(load_completion_diagnostics, "_load_database_diagnostics", lambda *args: {})
    monkeypatch.setattr(load_completion_diagnostics, "_load_consumer_metrics", lambda *args: {})
    sender = MagicMock()
    load_completion_diagnostics._diagnostic_worker(sender, "unused", "unused", "isolated", {})
    result = json.loads(sender.send_bytes.call_args.args[0])
    assert result["probes"]["consumer_offsets"] == {
        "status": "unavailable",
        "reason": "RuntimeConfigurationError",
    }
    factory.assert_not_called()
