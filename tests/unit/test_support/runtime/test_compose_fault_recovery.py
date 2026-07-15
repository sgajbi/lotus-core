"""Verify deterministic Compose fault injection and unconditional runtime recovery."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from tests.test_support.runtime.compose_fault_recovery import (
    CommandRunner,
    ComposeFaultRecoveryBoundary,
    ReadinessProbe,
)


def _successful_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, "", "")


def _ready() -> None:
    pass


def _boundary(
    *,
    runner: CommandRunner = _successful_run,
    faulted_service_ready: ReadinessProbe = _ready,
    recovery_services_ready: ReadinessProbe = _ready,
) -> ComposeFaultRecoveryBoundary:
    return ComposeFaultRecoveryBoundary(
        project_name="lotus-e2e",
        faulted_service="postgres",
        recovery_services=("ingestion_service", "persistence_service"),
        faulted_service_ready=faulted_service_ready,
        recovery_services_ready=recovery_services_ready,
        runner=runner,
    )


def test_restore_reconciles_database_and_restarts_dependents_once() -> None:
    runner = MagicMock(side_effect=_successful_run)
    faulted_service_ready = MagicMock()
    recovery_services_ready = MagicMock()
    boundary = _boundary(
        runner=runner,
        faulted_service_ready=faulted_service_ready,
        recovery_services_ready=recovery_services_ready,
    )

    with boundary as active_boundary:
        active_boundary.restore()

    commands = [call.args[0] for call in runner.call_args_list]
    assert commands == [
        ["docker", "compose", "-p", "lotus-e2e", "stop", "postgres"],
        [
            "docker",
            "compose",
            "-p",
            "lotus-e2e",
            "up",
            "--detach",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "60",
            "postgres",
        ],
        [
            "docker",
            "compose",
            "-p",
            "lotus-e2e",
            "restart",
            "ingestion_service",
            "persistence_service",
        ],
    ]
    faulted_service_ready.assert_called_once_with()
    recovery_services_ready.assert_called_once_with()


def test_restore_can_target_compose_file_without_restarting_unrelated_services() -> None:
    runner = MagicMock(side_effect=_successful_run)
    recovery_services_ready = MagicMock()
    boundary = ComposeFaultRecoveryBoundary(
        project_name="lotus-fx-proof",
        compose_file="C:/repo/docker-compose.yml",
        faulted_service="valuation_orchestrator_service",
        recovery_services=(),
        faulted_service_ready=_ready,
        recovery_services_ready=recovery_services_ready,
        runner=runner,
    )

    with boundary:
        pass

    commands = [call.args[0] for call in runner.call_args_list]
    assert commands == [
        [
            "docker",
            "compose",
            "-p",
            "lotus-fx-proof",
            "-f",
            "C:/repo/docker-compose.yml",
            "stop",
            "valuation_orchestrator_service",
        ],
        [
            "docker",
            "compose",
            "-p",
            "lotus-fx-proof",
            "-f",
            "C:/repo/docker-compose.yml",
            "up",
            "--detach",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "60",
            "valuation_orchestrator_service",
        ],
    ]
    recovery_services_ready.assert_not_called()


def test_context_exit_recovers_after_primary_failure() -> None:
    runner = MagicMock(side_effect=_successful_run)
    boundary = _boundary(runner=runner)

    with pytest.raises(ValueError, match="primary failure"):
        with boundary:
            raise ValueError("primary failure")

    assert boundary._restored is True
    assert runner.call_count == 3


def test_context_entry_recovers_then_reraises_stop_failure() -> None:
    stop_failure = subprocess.CalledProcessError(1, ["docker", "compose", "stop"])
    runner = MagicMock(
        side_effect=[
            stop_failure,
            _successful_run([]),
            _successful_run([]),
        ]
    )
    boundary = _boundary(runner=runner)

    with pytest.raises(subprocess.CalledProcessError) as raised:
        with boundary:
            pytest.fail("context body must not execute after failed fault injection")

    assert raised.value is stop_failure
    assert boundary._restored is True
    assert [call.args[0][4] for call in runner.call_args_list] == ["stop", "up", "restart"]


def test_context_entry_preserves_stop_failure_when_recovery_also_fails() -> None:
    stop_failure = subprocess.CalledProcessError(1, ["docker", "compose", "stop"])
    recovery_failure = subprocess.CalledProcessError(1, ["docker", "compose", "up"])
    runner = MagicMock(side_effect=[stop_failure, recovery_failure])
    boundary = _boundary(runner=runner)

    with pytest.raises(subprocess.CalledProcessError) as raised:
        with boundary:
            pytest.fail("context body must not execute after failed fault injection")

    assert raised.value is stop_failure
    assert raised.value.__notes__ == [
        "Docker Compose recovery also failed: "
        "CalledProcessError: Command '['docker', 'compose', 'up']' returned non-zero exit status 1."
    ]


def test_context_exit_preserves_primary_failure_when_recovery_also_fails() -> None:
    recovery_failure = subprocess.CalledProcessError(1, ["docker", "compose", "up"])
    runner = MagicMock(side_effect=[_successful_run([]), recovery_failure])
    boundary = _boundary(runner=runner)

    with pytest.raises(ValueError, match="primary failure") as raised:
        with boundary:
            raise ValueError("primary failure")

    assert raised.value.__notes__ == [
        "Docker Compose recovery also failed: "
        "CalledProcessError: Command '['docker', 'compose', 'up']' returned non-zero exit status 1."
    ]


def test_context_exit_raises_recovery_failure_without_primary_failure() -> None:
    recovery_failure = subprocess.CalledProcessError(1, ["docker", "compose", "up"])
    runner = MagicMock(side_effect=[_successful_run([]), recovery_failure])
    boundary = _boundary(runner=runner)

    with pytest.raises(subprocess.CalledProcessError):
        with boundary:
            pass
