import json
from pathlib import Path

from scripts.institutional_signoff_pack import (
    _completion_lag_seconds,
    _docker_smoke_status,
    _failure_recovery_status,
    _latency_status,
    _latest_artifact,
    _latest_load_reconciliation_artifact,
    _latest_performance_artifact,
    _load_reconciliation_status,
    _performance_status,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_docker_smoke_status_handles_integer_failed_count(tmp_path: Path) -> None:
    artifact = tmp_path / "docker.json"
    _write_json(artifact, {"passed": True, "failed": 0})

    status = _docker_smoke_status(artifact)

    assert status.passed is True
    assert "failed_count=0" in status.summary


def test_latency_status_handles_error_list_shape(tmp_path: Path) -> None:
    artifact = tmp_path / "latency.json"
    _write_json(
        artifact,
        {
            "results": [
                {"p95_ms": 10.0, "p95_budget_ms": 50.0, "errors": []},
                {"p95_ms": 12.0, "p95_budget_ms": 50.0, "errors": []},
            ]
        },
    )

    status = _latency_status(artifact)

    assert status.passed is True
    assert "violations=0" in status.summary


def test_performance_status_reports_failed_profiles(tmp_path: Path) -> None:
    artifact = tmp_path / "performance.json"
    _write_json(
        artifact,
        {
            "overall_passed": False,
            "profiles": [
                {"profile_name": "steady_state", "checks_passed": True},
                {"profile_name": "burst", "checks_passed": False},
            ],
        },
    )

    status = _performance_status(artifact)

    assert status.passed is False
    assert "burst" in status.summary


def test_failure_recovery_status_uses_checks_passed(tmp_path: Path) -> None:
    artifact = tmp_path / "failure-recovery.json"
    _write_json(artifact, {"checks_passed": False, "failed_checks": ["timeout"]})

    status = _failure_recovery_status(artifact)

    assert status.passed is False
    assert "timeout" in status.summary


def test_latest_artifact_discovers_nested_download_paths(tmp_path: Path) -> None:
    nested = tmp_path / "output" / "task-runs"
    nested.mkdir(parents=True)
    artifact = nested / "20260305T082418Z-failure-recovery-gate.json"
    _write_json(artifact, {"checks_passed": True, "failed_checks": []})

    discovered = _latest_artifact(tmp_path, "*-failure-recovery-gate.json")

    assert discovered is not None
    assert discovered == artifact


def test_latest_performance_artifact_prefers_full_profile_tier(tmp_path: Path) -> None:
    fast_artifact = tmp_path / "20260419T090000Z-performance-load-gate.json"
    full_artifact = tmp_path / "20260419T080000Z-performance-load-gate.json"
    _write_json(
        fast_artifact,
        {"profile_tier": "fast", "overall_passed": True, "profiles": []},
    )
    _write_json(
        full_artifact,
        {"profile_tier": "full", "overall_passed": True, "profiles": []},
    )

    selected = _latest_performance_artifact(tmp_path)

    assert selected == full_artifact


def test_latest_performance_artifact_falls_back_to_latest_when_full_missing(
    tmp_path: Path,
) -> None:
    older_artifact = tmp_path / "20260419T080000Z-performance-load-gate.json"
    newer_artifact = tmp_path / "20260419T090000Z-performance-load-gate.json"
    _write_json(older_artifact, {"profile_tier": "fast", "overall_passed": True, "profiles": []})
    _write_json(newer_artifact, {"overall_passed": True, "profiles": []})

    selected = _latest_performance_artifact(tmp_path)

    assert selected == newer_artifact


def test_latest_load_reconciliation_artifact_prefers_exhaustive_artifact(
    tmp_path: Path,
) -> None:
    exhaustive_artifact = tmp_path / "20260419T080000-bank-day-load-reconciliation.json"
    sampled_artifact = tmp_path / "20260419T090000-bank-day-load-reconciliation.json"
    _write_json(
        exhaustive_artifact,
        {
            "portfolio_count_evaluated": 1000,
            "run_progress": {"portfolios_ingested": 1000},
            "summary": {},
        },
    )
    _write_json(
        sampled_artifact,
        {
            "portfolio_count_evaluated": 5,
            "run_progress": {"portfolios_ingested": 1000},
            "summary": {},
        },
    )

    selected = _latest_load_reconciliation_artifact(tmp_path)

    assert selected == exhaustive_artifact


def test_latest_load_reconciliation_artifact_falls_back_to_latest_when_exhaustive_missing(
    tmp_path: Path,
) -> None:
    older_artifact = tmp_path / "20260419T080000-bank-day-load-reconciliation.json"
    newer_artifact = tmp_path / "20260419T090000-bank-day-load-reconciliation.json"
    _write_json(
        older_artifact,
        {
            "portfolio_count_evaluated": 5,
            "run_progress": {"portfolios_ingested": 1000},
            "summary": {},
        },
    )
    _write_json(
        newer_artifact,
        {
            "portfolio_count_evaluated": 10,
            "run_progress": {"portfolios_ingested": 1000},
            "summary": {},
        },
    )

    selected = _latest_load_reconciliation_artifact(tmp_path)

    assert selected == newer_artifact


def test_load_reconciliation_status_requires_complete_reconciled_run(tmp_path: Path) -> None:
    artifact = tmp_path / "20260418T142850-bank-day-load-reconciliation.json"
    _write_json(
        artifact,
        {
            "portfolio_count_evaluated": 5,
            "run_progress": {
                "run_state": "COMPLETE",
                "operator_progress_state": "COMPLETE",
                "complete_portfolios": 1000,
                "portfolios_ingested": 1000,
                "latest_snapshot_materialized_at_utc": "2026-04-18T09:05:10.887768Z",
                "latest_portfolio_timeseries_materialized_at_utc": "2026-04-18T09:32:59.815258Z",
            },
            "summary": {
                "all_samples_reconciled": True,
                "all_position_counts_match_expected": True,
                "all_transaction_counts_match_expected": True,
                "all_market_values_match_expected": True,
            },
        },
    )

    status = _load_reconciliation_status(artifact, max_completion_lag_seconds=1800)

    assert status.passed is True
    assert "complete_portfolios=1000/1000" in status.summary
    assert "completion_lag_seconds=" in status.summary


def test_load_reconciliation_status_rejects_incomplete_or_unreconciled_artifact(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "20260418T091831-bank-day-load-reconciliation.json"
    _write_json(
        artifact,
        {
            "portfolio_count_evaluated": 5,
            "run_progress": {
                "run_state": "MATERIALIZING",
                "operator_progress_state": "SLOW",
                "complete_portfolios": 733,
                "portfolios_ingested": 1000,
                "latest_snapshot_materialized_at_utc": "2026-04-18T09:05:10.887768Z",
                "latest_portfolio_timeseries_materialized_at_utc": "2026-04-18T09:32:59.815258Z",
            },
            "summary": {
                "all_samples_reconciled": False,
                "all_position_counts_match_expected": True,
                "all_transaction_counts_match_expected": True,
                "all_market_values_match_expected": True,
            },
        },
    )

    status = _load_reconciliation_status(artifact, max_completion_lag_seconds=1800)

    assert status.passed is False
    assert "run_state=MATERIALIZING" in status.summary


def test_completion_lag_seconds_prefers_explicit_tail_fields() -> None:
    lag_seconds = _completion_lag_seconds(
        {
            "latest_snapshot_to_position_timeseries_tail_seconds": 1668.362283,
            "latest_position_timeseries_to_portfolio_timeseries_tail_seconds": 0.565207,
            "latest_snapshot_materialized_at_utc": "2026-04-18T09:05:10.887768Z",
            "latest_portfolio_timeseries_materialized_at_utc": "2026-04-18T09:32:59.815258Z",
        }
    )

    assert lag_seconds == 1668.92749


def test_load_reconciliation_status_rejects_excess_completion_lag(tmp_path: Path) -> None:
    artifact = tmp_path / "20260418T142850-bank-day-load-reconciliation.json"
    _write_json(
        artifact,
        {
            "portfolio_count_evaluated": 5,
            "run_progress": {
                "run_state": "COMPLETE",
                "operator_progress_state": "COMPLETE",
                "complete_portfolios": 1000,
                "portfolios_ingested": 1000,
                "latest_snapshot_to_position_timeseries_tail_seconds": 1700.0,
                "latest_position_timeseries_to_portfolio_timeseries_tail_seconds": 200.0,
            },
            "summary": {
                "all_samples_reconciled": True,
                "all_position_counts_match_expected": True,
                "all_transaction_counts_match_expected": True,
                "all_market_values_match_expected": True,
            },
        },
    )

    status = _load_reconciliation_status(artifact, max_completion_lag_seconds=1800)

    assert status.passed is False
    assert "completion_lag_seconds=1900.0" in status.summary
