"""Operate isolated Docker Compose test stacks with bounded recovery and diagnostics."""

from __future__ import annotations

import logging
import os
import random
import re
import subprocess
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable

import requests
import yaml
from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient

from tests.test_support.runtime_env import PreparedTestRuntime


class DockerStackError(RuntimeError):
    """Raised when docker stack bring-up or health checks fail."""


class DockerImagePullFailureClass(StrEnum):
    """Source-safe failure classes for required Docker image acquisition."""

    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    REGISTRY_UNAVAILABLE = "registry_unavailable"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class DockerImagePullPolicy:
    """Bound attempts, subprocess timeouts, and retry delay for image pulls."""

    max_attempts: int = 3
    timeout_seconds: float = 120.0
    initial_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 15.0
    jitter_ratio: float = 0.20

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("backoff values must be nonnegative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

    def retry_delay_seconds(
        self,
        failed_attempt: int,
        jitter: Callable[[float, float], float],
    ) -> float:
        base_delay = min(
            self.max_backoff_seconds,
            self.initial_backoff_seconds * (2 ** max(0, failed_attempt - 1)),
        )
        jitter_ceiling = base_delay * self.jitter_ratio
        return min(
            self.max_backoff_seconds,
            base_delay + jitter(0.0, jitter_ceiling),
        )

    @property
    def maximum_total_duration_seconds(self) -> float:
        """Return the maximum pull time including timeouts and retry delays."""
        retry_budget = sum(
            min(
                self.max_backoff_seconds,
                self.initial_backoff_seconds
                * (2 ** max(0, failed_attempt - 1))
                * (1 + self.jitter_ratio),
            )
            for failed_attempt in range(1, self.max_attempts)
        )
        return self.max_attempts * self.timeout_seconds + retry_budget


LOGGER = logging.getLogger(__name__)

_RATE_LIMIT_MARKERS = ("toomanyrequests", "too many requests", "rate limit", "status code: 429")
_RETRYABLE_PULL_MARKERS = (
    "context deadline exceeded",
    "connect: connection timed out",
    "client.timeout exceeded while awaiting headers",
    "tls handshake timeout",
    "i/o timeout",
    "connection reset by peer",
    "connection refused",
    "temporary failure",
    "service unavailable",
    "status code: 500",
    "status code: 502",
    "status code: 503",
    "status code: 504",
)


def _compose_base_args(
    compose_file: str,
    *,
    project_name: str | None = None,
) -> list[str]:
    selected_project = project_name or os.getenv("COMPOSE_PROJECT_NAME")
    args = ["docker", "compose"]
    if selected_project:
        args.extend(["-p", selected_project])
    args.extend(["-f", compose_file])
    return args


def ensure_docker_engine_available(
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    try:
        runner(["docker", "info"], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise DockerStackError(
            "Docker engine is not available. Start Docker Desktop/daemon before running "
            "integration or E2E tests."
        ) from exc


def _load_compose_pull_images(compose_file: str) -> list[str]:
    compose_path = Path(compose_file)
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    services = data.get("services", {})
    images: list[str] = []
    for service in services.values():
        if service.get("build"):
            continue
        image = service.get("image")
        if image and image not in images:
            images.append(image)
    return images


def ensure_required_images_available(
    compose_file: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    *,
    pull_policy: DockerImagePullPolicy = DockerImagePullPolicy(),
    sleeper: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    if os.getenv("LOTUS_TESTS_PULL_BASE_IMAGES", "true").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    missing_images: list[str] = []
    for image in _load_compose_pull_images(compose_file):
        result = runner(
            ["docker", "image", "inspect", image],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            missing_images.append(image)

    for image in missing_images:
        _pull_required_image(
            image,
            runner=runner,
            policy=pull_policy,
            sleeper=sleeper,
            jitter=jitter,
            clock=clock,
        )


def _pull_required_image(
    image: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess],
    policy: DockerImagePullPolicy,
    sleeper: Callable[[float], None],
    jitter: Callable[[float, float], float],
    clock: Callable[[], float],
) -> None:
    started_at = clock()
    last_failure = DockerImagePullFailureClass.PERMANENT
    for attempt in range(1, policy.max_attempts + 1):
        try:
            runner(
                ["docker", "pull", image],
                check=True,
                capture_output=True,
                timeout=policy.timeout_seconds,
            )
            LOGGER.info(
                "docker_image_pull_completed",
                extra={
                    "image": image,
                    "attempt": attempt,
                    "outcome": "success",
                    "elapsed_seconds": round(clock() - started_at, 3),
                },
            )
            return
        except subprocess.TimeoutExpired as exc:
            last_failure = DockerImagePullFailureClass.TIMEOUT
            pull_error: BaseException = exc
        except subprocess.CalledProcessError as exc:
            last_failure = _classify_image_pull_failure(_process_error_text(exc))
            pull_error = exc

        retrying = (
            last_failure is not DockerImagePullFailureClass.PERMANENT
            and attempt < policy.max_attempts
        )
        LOGGER.warning(
            "docker_image_pull_failed",
            extra={
                "image": image,
                "attempt": attempt,
                "failure_class": last_failure.value,
                "outcome": "retrying" if retrying else "failed",
                "elapsed_seconds": round(clock() - started_at, 3),
            },
        )
        if not retrying:
            elapsed_seconds = round(clock() - started_at, 3)
            raise DockerStackError(
                "Failed to pull required Docker image "
                f"'{image}' (failure_class={last_failure.value}, attempts={attempt}, "
                f"elapsed_seconds={elapsed_seconds}, "
                f"budget_seconds={policy.maximum_total_duration_seconds})"
            ) from pull_error

        sleeper(policy.retry_delay_seconds(attempt, jitter))


def _process_error_text(error: subprocess.CalledProcessError) -> str:
    stderr = error.stderr or b""
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="ignore").lower()
    return str(stderr).lower()


def _classify_image_pull_failure(details: str) -> DockerImagePullFailureClass:
    normalized_details = details.lower()
    if any(marker in normalized_details for marker in _RATE_LIMIT_MARKERS):
        return DockerImagePullFailureClass.RATE_LIMITED
    if any(marker in normalized_details for marker in _RETRYABLE_PULL_MARKERS):
        return DockerImagePullFailureClass.REGISTRY_UNAVAILABLE
    return DockerImagePullFailureClass.PERMANENT


def _is_retryable_compose_up_error(stderr: str) -> bool:
    retryable_markers = (
        "already exists",
        "container name",
        "is already in use",
        "no such container",
        "pulling",
        "didn't complete successfully: exit",
        "context deadline exceeded",
        "tls handshake timeout",
        "connection reset by peer",
        "toomanyrequests",
        "service unavailable",
        "i/o timeout",
    )
    lowered = stderr.lower()
    return any(marker in lowered for marker in retryable_markers)


def _is_host_port_bind_error(stderr: str) -> bool:
    bind_markers = (
        "address already in use",
        "port is already allocated",
        "failed to bind host port",
        "bind for 0.0.0.0",
        "listen tcp",
        "only one usage of each socket address",
    )
    lowered = stderr.lower()
    return any(marker in lowered for marker in bind_markers)


def should_build_images() -> bool:
    return os.getenv("LOTUS_TESTS_DOCKER_BUILD", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def compose_up(
    compose_file: str,
    *,
    build: bool,
    services: list[str] | None = None,
    retries: int = 2,
    retry_wait_seconds: int = 5,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    runtime: PreparedTestRuntime | None = None,
) -> None:
    project_name = runtime.endpoints.compose_project_name if runtime is not None else None
    compose_environment = runtime.values if runtime is not None else None
    compose_args = _compose_base_args(compose_file, project_name=project_name)
    ensure_docker_engine_available(runner)
    ensure_required_images_available(compose_file, runner)
    _remove_stale_project_containers(compose_file, runner, project_name=project_name)
    try:
        runner(
            [*compose_args, "down", "--remove-orphans"],
            check=False,
            capture_output=True,
            env=compose_environment,
        )
    except subprocess.CalledProcessError:
        # Best-effort cleanup only. Continue with bring-up retries.
        pass

    if build:
        build_args = [*compose_args, "build"]
        if services:
            build_args.extend(services)
        try:
            runner(
                build_args,
                check=True,
                capture_output=True,
                env=compose_environment,
            )
        except subprocess.CalledProcessError as exc:
            if runtime is not None:
                runtime.port_reservation.release()
            details = _process_error_text(exc).strip()
            raise DockerStackError(f"docker compose build failed: {details}") from exc

    args = [*compose_args, "up"]
    args.append("-d")
    if services:
        args.extend(services)

    attempts = max(1, retries + 1)
    last_error: subprocess.CalledProcessError | None = None
    last_bind_conflict = False
    attempts_used = 0
    port_reallocations = 0
    for attempt in range(1, attempts + 1):
        attempts_used = attempt
        if runtime is not None:
            runtime.port_reservation.release()
        try:
            runner(
                args,
                check=True,
                capture_output=True,
                env=compose_environment,
            )
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            stderr = _process_error_text(exc)
            last_bind_conflict = _is_host_port_bind_error(stderr)
            removed_conflicts = _remove_conflicting_named_containers(stderr, runner)
            can_retry = attempt < attempts and (
                removed_conflicts
                or _is_retryable_compose_up_error(stderr)
                or (last_bind_conflict and runtime is not None)
            )
            if can_retry:
                try:
                    runner(
                        [*compose_args, "down", "--remove-orphans"],
                        check=False,
                        capture_output=True,
                        env=compose_environment,
                    )
                except subprocess.CalledProcessError:
                    # Retry path should not fail due to cleanup issues.
                    pass
                if last_bind_conflict and runtime is not None:
                    try:
                        runtime.port_reservation.reallocate()
                    except OSError as reservation_error:
                        raise DockerStackError(
                            "docker compose host-port reallocation failed "
                            f"(attempt={attempt}, compose_project="
                            f"{project_name or 'unknown'})"
                        ) from reservation_error
                    port_reallocations += 1
                    LOGGER.warning(
                        "Reallocated test runtime host ports after Compose bind conflict.",
                        extra={
                            "attempt": attempt,
                            "port_reallocations": port_reallocations,
                            "compose_project": project_name or "unknown",
                        },
                    )
                if retry_wait_seconds > 0:
                    time.sleep(retry_wait_seconds)
                continue
            break

    message = "docker compose up failed"
    if last_bind_conflict:
        message = (
            f"{message} (failure_class=host_port_bind_conflict, "
            f"attempts={attempts_used}, port_reallocations={port_reallocations}, "
            f"compose_project={project_name or 'unknown'})"
        )
    if last_error:
        details = _process_error_text(last_error).strip()
        message = f"{message}: {details}"
    raise DockerStackError(message)


def wait_for_migration_runner(
    compose_file: str,
    *,
    timeout_seconds: int = 120,
    poll_seconds: int = 2,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    wait_for_compose_service_success(
        compose_file,
        "migration-runner",
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
        runner=runner,
    )


def wait_for_compose_service_success(
    compose_file: str,
    service_name: str,
    *,
    timeout_seconds: int = 120,
    poll_seconds: int = 2,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    ensure_docker_engine_available(runner)
    start = time.time()
    while time.time() - start < timeout_seconds:
        result = runner(
            [*_compose_base_args(compose_file), "ps", "--status=exited", "-q", service_name],
            capture_output=True,
            text=True,
            check=True,
        )
        container_id = result.stdout.strip()
        if not container_id:
            time.sleep(poll_seconds)
            continue

        exit_code_result = runner(
            ["docker", "inspect", container_id, "--format", "{{.State.ExitCode}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        if exit_code_result.stdout.strip() == "0":
            return

        logs_result = runner(
            [*_compose_base_args(compose_file), "logs", service_name],
            capture_output=True,
            text=True,
            check=False,
        )
        raise DockerStackError(
            f"{service_name} exited with non-zero status:\n" + logs_result.stdout
        )

    logs_result = runner(
        [*_compose_base_args(compose_file), "logs", service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    raise DockerStackError(
        f"{service_name} did not complete within {timeout_seconds}s:\n{logs_result.stdout}"
    )


def wait_for_http_health(
    service_name: str,
    health_url: str,
    *,
    timeout_seconds: int = 120,
    poll_seconds: int = 3,
    get: Callable[..., requests.Response] = requests.get,
) -> None:
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            response = get(health_url, timeout=2)
            if response.status_code == 200:
                return
        except requests.ConnectionError:
            pass
        time.sleep(poll_seconds)

    raise DockerStackError(
        f"Service '{service_name}' did not become healthy within {timeout_seconds} seconds."
    )


def wait_for_kafka_metadata(
    bootstrap_servers: str,
    *,
    timeout_seconds: int = 120,
    poll_seconds: int = 2,
) -> None:
    start = time.time()
    admin_client = AdminClient({"bootstrap.servers": bootstrap_servers})
    while time.time() - start < timeout_seconds:
        try:
            admin_client.list_topics(timeout=5)
            return
        except (KafkaException, Exception):
            time.sleep(poll_seconds)

    raise DockerStackError(
        f"Kafka broker at '{bootstrap_servers}' did not become metadata-ready within "
        f"{timeout_seconds} seconds."
    )


def compose_down(
    compose_file: str,
    *,
    runtime: PreparedTestRuntime | None = None,
) -> None:
    ensure_docker_engine_available()
    project_name = runtime.endpoints.compose_project_name if runtime is not None else None
    subprocess.run(
        [
            *_compose_base_args(compose_file, project_name=project_name),
            "down",
            "-v",
            "--remove-orphans",
        ],
        check=False,
        capture_output=True,
        env=runtime.values if runtime is not None else None,
    )


def capture_compose_logs(
    compose_file: str,
    output_path: str | Path,
    *,
    runtime: PreparedTestRuntime | None = None,
) -> None:
    """Capture logs for the active compose project before teardown."""
    ensure_docker_engine_available()
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    project_name = runtime.endpoints.compose_project_name if runtime is not None else None
    result = subprocess.run(
        [
            *_compose_base_args(compose_file, project_name=project_name),
            "logs",
            "--no-color",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=runtime.values if runtime is not None else None,
    )
    log_text = result.stdout
    if result.stderr:
        log_text = f"{log_text}\n--- docker compose logs stderr ---\n{result.stderr}"
    destination.write_text(log_text, encoding="utf-8")


def _remove_conflicting_named_containers(
    stderr: str,
    runner: Callable[..., subprocess.CompletedProcess],
) -> bool:
    removed_any = False
    matches = re.findall(r'container name "/([^"]+)" is already in use', stderr)
    for container_name in matches:
        runner(["docker", "rm", "-f", container_name], check=False, capture_output=True)
        removed_any = True
    return removed_any


def _remove_stale_project_containers(
    compose_file: str,
    runner: Callable[..., subprocess.CompletedProcess],
    *,
    project_name: str | None = None,
) -> None:
    selected_project = project_name or os.getenv("COMPOSE_PROJECT_NAME")
    if not selected_project:
        selected_project = Path(compose_file).resolve().parent.name
    try:
        ps = runner(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={selected_project}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return

    if not ps.stdout:
        return

    container_ids = [line.strip() for line in ps.stdout.splitlines() if line.strip()]
    if not container_ids:
        return

    runner(["docker", "rm", "-f", *container_ids], check=False, capture_output=True)


def resolve_compose_file(project_root: str) -> str:
    return str(Path(project_root) / "docker-compose.yml")
