from pathlib import Path

import pytest

from scripts.failure_recovery_gate import (
    RecoveryMode,
    _evaluate_recovery_result,
    _pause_container,
    _resolve_interruption_container,
    _unpause_container,
)


def test_resolve_interruption_container_prefers_compose_resolved_container_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.failure_recovery_gate._run_capture",
        lambda cmd, cwd: "abc123containerid\n",
    )

    resolved = _resolve_interruption_container(
        repo_root=Path("."),
        compose_file="docker-compose.yml",
        interruption_container="persistence_service",
    )

    assert resolved == "abc123containerid"


def test_resolve_interruption_container_falls_back_to_raw_input_when_service_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.failure_recovery_gate._run_capture",
        lambda cmd, cwd: "",
    )

    resolved = _resolve_interruption_container(
        repo_root=Path("."),
        compose_file="docker-compose.yml",
        interruption_container="persistence_service",
    )

    assert resolved == "persistence_service"


def test_resolve_interruption_container_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        _resolve_interruption_container(
            repo_root=Path("."),
            compose_file="docker-compose.yml",
            interruption_container=" ",
        )


def test_pause_and_unpause_use_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], Path]] = []

    def _fake_run(cmd: list[str], cwd: Path) -> None:
        calls.append((cmd, cwd))

    monkeypatch.setattr("scripts.failure_recovery_gate._run", _fake_run)

    repo_root = Path("/tmp/repo")
    _pause_container("container-id", repo_root=repo_root)
    _unpause_container("container-id", repo_root=repo_root)

    assert calls == [
        (["docker", "pause", "container-id"], repo_root),
        (["docker", "unpause", "container-id"], repo_root),
    ]


def test_evaluate_recovery_result_marks_fully_drained_when_all_checks_clear() -> None:
    mode, failed_checks = _evaluate_recovery_result(
        backlog_growth_jobs=20,
        drain_seconds_to_baseline=180.0,
        backlog_age_seconds_after_recovery=45.0,
        dlq_pressure_ratio_after_recovery=0.2,
        replay_pressure_ratio_after_recovery=0.01,
    )

    assert mode is RecoveryMode.FULLY_DRAINED
    assert failed_checks == []


def test_evaluate_recovery_result_marks_bounded_recovery_when_timeout_is_bounded() -> None:
    mode, failed_checks = _evaluate_recovery_result(
        backlog_growth_jobs=20,
        drain_seconds_to_baseline=None,
        backlog_age_seconds_after_recovery=500.0,
        dlq_pressure_ratio_after_recovery=4.8,
        replay_pressure_ratio_after_recovery=0.0052,
    )

    assert mode is RecoveryMode.BOUNDED_RECOVERY
    assert failed_checks == []


@pytest.mark.parametrize(
    ("kwargs", "expected_fragment"),
    [
        (
            {
                "backlog_growth_jobs": 1,
                "drain_seconds_to_baseline": 120.0,
                "backlog_age_seconds_after_recovery": 10.0,
                "dlq_pressure_ratio_after_recovery": 0.0,
                "replay_pressure_ratio_after_recovery": 0.0,
            },
            "backlog growth during interruption was too small",
        ),
        (
            {
                "backlog_growth_jobs": 10,
                "drain_seconds_to_baseline": 421.0,
                "backlog_age_seconds_after_recovery": 10.0,
                "dlq_pressure_ratio_after_recovery": 0.0,
                "replay_pressure_ratio_after_recovery": 0.0,
            },
            "recovery drain 421.00s exceeded max 420.00s",
        ),
        (
            {
                "backlog_growth_jobs": 10,
                "drain_seconds_to_baseline": None,
                "backlog_age_seconds_after_recovery": 1201.0,
                "dlq_pressure_ratio_after_recovery": 0.0,
                "replay_pressure_ratio_after_recovery": 0.0,
            },
            "recovery drain timeout with elevated backlog age",
        ),
        (
            {
                "backlog_growth_jobs": 10,
                "drain_seconds_to_baseline": 120.0,
                "backlog_age_seconds_after_recovery": 1801.0,
                "dlq_pressure_ratio_after_recovery": 0.0,
                "replay_pressure_ratio_after_recovery": 0.0,
            },
            "backlog age after recovery 1801.00s exceeded 1800s",
        ),
        (
            {
                "backlog_growth_jobs": 10,
                "drain_seconds_to_baseline": 120.0,
                "backlog_age_seconds_after_recovery": 10.0,
                "dlq_pressure_ratio_after_recovery": 5.1,
                "replay_pressure_ratio_after_recovery": 0.0,
            },
            "DLQ pressure after recovery 5.1000 exceeded 5.0000",
        ),
        (
            {
                "backlog_growth_jobs": 10,
                "drain_seconds_to_baseline": 120.0,
                "backlog_age_seconds_after_recovery": 10.0,
                "dlq_pressure_ratio_after_recovery": 0.0,
                "replay_pressure_ratio_after_recovery": 5.1,
            },
            "Replay pressure after recovery 5.1000 exceeded 5.0000",
        ),
    ],
)
def test_evaluate_recovery_result_marks_failed_recovery_for_threshold_breaches(
    kwargs: dict[str, float | None],
    expected_fragment: str,
) -> None:
    mode, failed_checks = _evaluate_recovery_result(**kwargs)

    assert mode is RecoveryMode.FAILED_RECOVERY
    assert any(expected_fragment in check for check in failed_checks)
