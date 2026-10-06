"""Verify deterministic Compose fault injection and unconditional runtime recovery."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from tests.test_support.runtime.compose_fault_recovery import (
    CommandRunner,
    ComposeFaultRecoveryBoundary,
    ReadinessProbe,
    wait_for_owned_container_exit,
)


def _successful_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, "", "")


def _ready() -> None:
    pass


def test_original_container_exit_precedes_restore_and_restore_remains_idempotent(monkeypatch):
    from tests.test_support import native_consumer_boundary

    commands = []
    states = iter([("running", True), ("stopping", True), ("exited", False)])
    observed = []

    def inspect_runner(command, **kwargs):
        commands.append(command)
        assert command == ["docker", "inspect", "original"]
        assert kwargs["check"] is True
        status, running = next(states)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                [
                    {
                        "Id": "original",
                        "Config": {
                            "Labels": {
                                "com.docker.compose.project": "lotus-e2e",
                                "com.docker.compose.service": "postgres",
                            }
                        },
                        "State": {"Status": status, "Running": running},
                    }
                ]
            ),
            "",
        )

    def poll(observe, accept):
        for _ in range(3):
            state = observe()
            observed.append(state["Status"])
            if accept(state):
                return state
        pytest.fail("Exit was never observed")

    monkeypatch.setattr(native_consumer_boundary, "wait_for_value", poll)
    wait_for_owned_container_exit(
        "original",
        project_name="lotus-e2e",
        service_name="postgres",
        runner=inspect_runner,
    )
    boundary = _boundary(
        runner=lambda command, **kwargs: commands.append(command) or _successful_run(command)
    )
    boundary.restore()
    boundary.restore()
    assert observed == ["running", "stopping", "exited"]
    assert all(command == ["docker", "inspect", "original"] for command in commands[:3])
    assert commands[3][4] == "up"
    assert sum("up" in command for command in commands) == 1
    assert sum("restart" in command for command in commands) == 1


@pytest.mark.parametrize("wrong_label", ["project", "service"])
def test_exit_observation_refuses_foreign_container(monkeypatch, wrong_label):
    from tests.test_support import native_consumer_boundary

    monkeypatch.setattr(
        native_consumer_boundary, "wait_for_value", lambda observe, accept: observe()
    )
    labels = {"com.docker.compose.project": "lotus-e2e", "com.docker.compose.service": "postgres"}
    labels[f"com.docker.compose.{wrong_label}"] = "foreign"
    runner = MagicMock(
        return_value=subprocess.CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Id": "original",
                        "Config": {"Labels": labels},
                        "State": {"Status": "exited", "Running": False},
                    }
                ]
            ),
            "",
        )
    )
    with pytest.raises(ValueError, match="outside the owned service"):
        wait_for_owned_container_exit(
            "original",
            project_name="lotus-e2e",
            service_name="postgres",
            runner=runner,
        )
    runner.assert_called_once()


def test_exit_observation_does_not_accept_running_state(monkeypatch):
    from tests.test_support import native_consumer_boundary

    def poll(observe, accept):
        assert not accept(observe())
        raise TimeoutError("still running")

    monkeypatch.setattr(native_consumer_boundary, "wait_for_value", poll)
    runner = MagicMock(
        return_value=subprocess.CompletedProcess(
            [],
            0,
            json.dumps(
                [
                    {
                        "Id": "original",
                        "Config": {
                            "Labels": {
                                "com.docker.compose.project": "lotus-e2e",
                                "com.docker.compose.service": "postgres",
                            }
                        },
                        "State": {"Status": "running", "Running": True},
                    }
                ]
            ),
            "",
        )
    )
    with pytest.raises(TimeoutError, match="still running"):
        wait_for_owned_container_exit(
            "original",
            project_name="lotus-e2e",
            service_name="postgres",
            runner=runner,
        )


@pytest.mark.parametrize("payload", ["not-json", "[]", "[{}]"])
def test_exit_observation_refuses_malformed_inspection(monkeypatch, payload):
    from tests.test_support import native_consumer_boundary

    monkeypatch.setattr(
        native_consumer_boundary, "wait_for_value", lambda observe, accept: observe()
    )
    runner = MagicMock(return_value=subprocess.CompletedProcess([], 0, payload, ""))
    with pytest.raises((ValueError, KeyError)):
        wait_for_owned_container_exit(
            "original",
            project_name="lotus-e2e",
            service_name="postgres",
            runner=runner,
        )


@pytest.mark.parametrize(
    "container_id,state,expected_error",
    [
        ("foreign", {"Status": "exited", "Running": False}, "original identity"),
        ("original", {"Status": "exited", "Running": "false"}, "malformed exit state"),
    ],
)
def test_exit_observation_refuses_mismatched_identity_or_malformed_state(
    monkeypatch,
    container_id,
    state,
    expected_error,
):
    from tests.test_support import native_consumer_boundary

    monkeypatch.setattr(
        native_consumer_boundary, "wait_for_value", lambda observe, accept: observe()
    )
    payload = [
        {
            "Id": container_id,
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "lotus-e2e",
                    "com.docker.compose.service": "postgres",
                }
            },
            "State": state,
        }
    ]
    runner = MagicMock(return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), ""))
    with pytest.raises(ValueError, match=expected_error):
        wait_for_owned_container_exit(
            "original",
            project_name="lotus-e2e",
            service_name="postgres",
            runner=runner,
        )


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
    assert boundary.recovery_evidence is not None
    assert boundary.recovery_evidence.faulted_service == "valuation_orchestrator_service"
    assert boundary.recovery_evidence.compose_health_wait_passed is True
    assert boundary.recovery_evidence.outage_duration_seconds >= 0


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
