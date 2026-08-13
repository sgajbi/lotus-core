"""Certify bounded Kafka recovery after an interrupted app-local broker session."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.test_support.docker_stack import wait_for_compose_service_success  # noqa: E402
from tests.test_support.managed_compose_run import prepare_managed_compose_run  # noqa: E402

KAFKA_SERVICE = "kafka"
ZOOKEEPER_SERVICE = "zookeeper"
TOPIC_CREATOR_SERVICE = "kafka-topic-creator"
DEPENDENT_SERVICE = "ingestion_service"


class KafkaRestartRecoveryError(RuntimeError):
    """Raised when bounded app-local broker recovery cannot be proven."""


@dataclass(frozen=True, slots=True)
class BrokerState:
    container_id: str
    status: str
    restart_count: int


@dataclass(frozen=True, slots=True)
class KafkaRestartRecoveryEvidence:
    compose_project: str
    interrupted_container_id: str
    recovered_container_id: str
    recovery_restart_count: int
    recovery_elapsed_seconds: float
    clean_restart_cycles: int
    topic_creator_exit_code: int
    dependent_service_status: str


def wait_for_healthy_broker(
    state_reader: Callable[[], BrokerState],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float = 2.0,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> BrokerState:
    """Wait for health within one explicit budget and return source-safe failure evidence."""

    deadline = monotonic() + timeout_seconds
    last_state = state_reader()
    while last_state.status != "healthy" and monotonic() < deadline:
        sleeper(poll_interval_seconds)
        last_state = state_reader()
    if last_state.status != "healthy":
        raise KafkaRestartRecoveryError(
            recovery_failure_diagnostic(last_state, timeout_seconds=timeout_seconds)
        )
    return last_state


def recovery_failure_diagnostic(state: BrokerState, *, timeout_seconds: float) -> str:
    return (
        "Kafka broker recovery budget exhausted "
        f"(status={state.status}, restart_count={state.restart_count}, "
        f"timeout_seconds={timeout_seconds:g}). Inspect the exact Compose project for a live "
        "competing broker session; do not delete ZooKeeper or application volumes as the default "
        "remediation."
    )


def run_recovery_gate(args: argparse.Namespace) -> KafkaRestartRecoveryEvidence:
    compose_file = Path(args.compose_file).resolve()
    log_path = Path(args.log_path).resolve()
    managed = prepare_managed_compose_run(
        profile="kafka-restart",
        scope="broker-session-recovery",
        compose_project_name=args.compose_project,
        compose_file=compose_file,
        services=(ZOOKEEPER_SERVICE, KAFKA_SERVICE, TOPIC_CREATOR_SERVICE),
        build=args.build,
        log_path=log_path,
        keep_stack=args.keep_compose,
        reset_volumes=False,
        startup_timeout_seconds=args.startup_timeout_seconds,
    )
    environment = managed.runtime.values
    with managed:
        wait_for_compose_service_success(
            managed.compose_file,
            TOPIC_CREATOR_SERVICE,
            timeout_seconds=int(args.startup_timeout_seconds),
            runtime=managed.runtime,
        )
        interrupted_container_id = _compose_container_id(
            managed.compose_command,
            KAFKA_SERVICE,
            environment=environment,
        )
        _assert_container_owner(
            interrupted_container_id,
            project=managed.runtime.endpoints.compose_project_name,
            service=KAFKA_SERVICE,
            environment=environment,
        )
        _run(["docker", "kill", interrupted_container_id], environment=environment)
        _run(["docker", "rm", interrupted_container_id], environment=environment)

        recovery_started = time.monotonic()
        _run(managed.compose_command("up", "-d", KAFKA_SERVICE), environment=environment)
        recovered = wait_for_healthy_broker(
            lambda: _read_broker_state(managed.compose_command, environment=environment),
            timeout_seconds=args.recovery_timeout_seconds,
        )
        recovery_elapsed = round(time.monotonic() - recovery_started, 3)
        if recovered.container_id == interrupted_container_id:
            raise KafkaRestartRecoveryError("Kafka interruption did not create a new container.")

        _run(
            managed.compose_command(
                "up",
                "-d",
                "--force-recreate",
                TOPIC_CREATOR_SERVICE,
            ),
            environment=environment,
        )
        wait_for_compose_service_success(
            managed.compose_file,
            TOPIC_CREATOR_SERVICE,
            timeout_seconds=int(args.recovery_timeout_seconds),
            runtime=managed.runtime,
        )
        topic_creator_exit_code = _service_exit_code(
            managed.compose_command,
            TOPIC_CREATOR_SERVICE,
            environment=environment,
        )
        if topic_creator_exit_code != 0:
            raise KafkaRestartRecoveryError(
                "Kafka topic creator did not complete successfully "
                f"(exit_code={topic_creator_exit_code})."
            )

        for _ in range(args.clean_restart_cycles):
            _run(managed.compose_command("stop", KAFKA_SERVICE), environment=environment)
            _run(managed.compose_command("start", KAFKA_SERVICE), environment=environment)
            wait_for_healthy_broker(
                lambda: _read_broker_state(managed.compose_command, environment=environment),
                timeout_seconds=args.recovery_timeout_seconds,
            )

        _run(
            managed.compose_command("up", "-d", "--no-deps", DEPENDENT_SERVICE),
            environment=environment,
        )
        dependent = _wait_for_service_health(
            managed.compose_command,
            DEPENDENT_SERVICE,
            environment=environment,
            timeout_seconds=args.recovery_timeout_seconds,
        )
        return KafkaRestartRecoveryEvidence(
            compose_project=managed.runtime.endpoints.compose_project_name,
            interrupted_container_id=interrupted_container_id,
            recovered_container_id=recovered.container_id,
            recovery_restart_count=recovered.restart_count,
            recovery_elapsed_seconds=recovery_elapsed,
            clean_restart_cycles=args.clean_restart_cycles,
            topic_creator_exit_code=topic_creator_exit_code,
            dependent_service_status=dependent.status,
        )


def _wait_for_service_health(
    command_builder: Callable[..., list[str]],
    service: str,
    *,
    environment: dict[str, str],
    timeout_seconds: float,
) -> BrokerState:
    return wait_for_healthy_broker(
        lambda: _read_service_state(command_builder, service, environment=environment),
        timeout_seconds=timeout_seconds,
    )


def _read_broker_state(
    command_builder: Callable[..., list[str]], *, environment: dict[str, str]
) -> BrokerState:
    return _read_service_state(command_builder, KAFKA_SERVICE, environment=environment)


def _read_service_state(
    command_builder: Callable[..., list[str]],
    service: str,
    *,
    environment: dict[str, str],
) -> BrokerState:
    container_id = _compose_container_id(command_builder, service, environment=environment)
    raw = _capture(
        [
            "docker",
            "inspect",
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}"
            "{{.State.Status}}{{end}}|{{.RestartCount}}",
            container_id,
        ],
        environment=environment,
    )
    status, restart_count = raw.split("|", maxsplit=1)
    return BrokerState(container_id, status, int(restart_count))


def _service_exit_code(
    command_builder: Callable[..., list[str]],
    service: str,
    *,
    environment: dict[str, str],
) -> int:
    container_id = _compose_container_id(
        command_builder,
        service,
        environment=environment,
        include_stopped=True,
    )
    return int(
        _capture(
            ["docker", "inspect", "--format", "{{.State.ExitCode}}", container_id],
            environment=environment,
        )
    )


def _compose_container_id(
    command_builder: Callable[..., list[str]],
    service: str,
    *,
    environment: dict[str, str],
    include_stopped: bool = False,
) -> str:
    flag = "-aq" if include_stopped else "-q"
    container_id = _capture(command_builder("ps", flag, service), environment=environment)
    if not container_id:
        raise KafkaRestartRecoveryError(f"Compose service has no container: {service}")
    return container_id


def _assert_container_owner(
    container_id: str,
    *,
    project: str,
    service: str,
    environment: dict[str, str],
) -> None:
    owner = _capture(
        [
            "docker",
            "inspect",
            "--format",
            '{{ index .Config.Labels "com.docker.compose.project" }}|'
            '{{ index .Config.Labels "com.docker.compose.service" }}',
            container_id,
        ],
        environment=environment,
    )
    expected = f"{project}|{service}"
    if owner != expected:
        raise KafkaRestartRecoveryError(
            "Refusing to interrupt container with unexpected ownership: "
            f"expected={expected}, actual={owner}"
        )


def _run(command: Sequence[str], *, environment: dict[str, str]) -> None:
    _execute(command, environment=environment, capture=False)


def _capture(command: Sequence[str], *, environment: dict[str, str]) -> str:
    return _execute(command, environment=environment, capture=True).strip()


def _execute(command: Sequence[str], *, environment: dict[str, str], capture: bool) -> str:
    completed = subprocess.run(
        list(command),
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise KafkaRestartRecoveryError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}; {detail}"
        )
    return completed.stdout or ""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", default=str(REPO_ROOT / "docker-compose.yml"))
    parser.add_argument("--compose-project")
    parser.add_argument(
        "--log-path",
        default=str(REPO_ROOT / "output" / "task-runs" / "kafka-restart-recovery.log"),
    )
    parser.add_argument("--startup-timeout-seconds", type=float, default=300.0)
    parser.add_argument("--recovery-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--clean-restart-cycles", type=int, default=2)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--keep-compose", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    evidence = run_recovery_gate(parse_args(argv))
    print(json.dumps(asdict(evidence), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
