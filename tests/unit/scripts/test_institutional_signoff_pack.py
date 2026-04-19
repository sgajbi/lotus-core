import json
from pathlib import Path

from scripts.institutional_signoff_pack import (
    _docker_smoke_status,
    _failure_recovery_status,
    _latency_status,
    _latest_artifact,
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
            },
            "summary": {
                "all_samples_reconciled": True,
                "all_position_counts_match_expected": True,
                "all_transaction_counts_match_expected": True,
                "all_market_values_match_expected": True,
            },
        },
    )

    status = _load_reconciliation_status(artifact)

    assert status.passed is True
    assert "complete_portfolios=1000/1000" in status.summary


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
            },
            "summary": {
                "all_samples_reconciled": False,
                "all_position_counts_match_expected": True,
                "all_transaction_counts_match_expected": True,
                "all_market_values_match_expected": True,
            },
        },
    )

    status = _load_reconciliation_status(artifact)

    assert status.passed is False
    assert "run_state=MATERIALIZING" in status.summary
