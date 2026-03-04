import json
from pathlib import Path

from scripts.institutional_signoff_pack import (
    _docker_smoke_status,
    _failure_recovery_status,
    _latency_status,
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
