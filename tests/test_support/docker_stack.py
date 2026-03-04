from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

import requests


class DockerStackError(RuntimeError):
    """Raised when docker stack bring-up or health checks fail."""


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
) -> None:
    _remove_stale_project_containers(compose_file, runner)
    try:
        runner(
            ["docker", "compose", "-f", compose_file, "down", "--remove-orphans"],
            check=False,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        # Best-effort cleanup only. Continue with bring-up retries.
        pass

    args = ["docker", "compose", "-f", compose_file, "up"]
    if build:
        args.append("--build")
    args.append("-d")
    if services:
        args.extend(services)

    attempts = max(1, retries + 1)
    last_error: subprocess.CalledProcessError | None = None
    for _ in range(attempts):
        try:
            runner(args, check=True, capture_output=True)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            stderr = (exc.stderr or b"").decode("utf-8", errors="ignore").lower()
            removed_conflicts = _remove_conflicting_named_containers(stderr, runner)
            if removed_conflicts or _is_retryable_compose_up_error(stderr):
                try:
                    runner(
                        ["docker", "compose", "-f", compose_file, "down", "--remove-orphans"],
                        check=False,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError:
                    # Retry path should not fail due to cleanup issues.
                    pass
                if retry_wait_seconds > 0:
                    time.sleep(retry_wait_seconds)
                continue
            break

    message = "docker compose up failed"
    if last_error:
        details = (last_error.stderr or b"").decode("utf-8", errors="ignore").strip()
        message = f"{message}: {details}"
    raise DockerStackError(message)


def wait_for_migration_runner(
    compose_file: str,
    *,
    timeout_seconds: int = 120,
    poll_seconds: int = 2,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    start = time.time()
    while time.time() - start < timeout_seconds:
        result = runner(
            [
                "docker",
                "compose",
                "-f",
                compose_file,
                "ps",
                "--status=exited",
                "-q",
                "migration-runner",
            ],
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
            ["docker", "compose", "-f", compose_file, "logs", "migration-runner"],
            capture_output=True,
            text=True,
            check=False,
        )
        raise DockerStackError(
            "migration-runner exited with non-zero status:\n" + logs_result.stdout
        )

    logs_result = runner(
        ["docker", "compose", "-f", compose_file, "logs", "migration-runner"],
        capture_output=True,
        text=True,
        check=False,
    )
    raise DockerStackError(
        f"migration-runner did not complete within {timeout_seconds}s:\n{logs_result.stdout}"
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


def compose_down(compose_file: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", compose_file, "down", "-v", "--remove-orphans"],
        check=False,
        capture_output=True,
    )


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
) -> None:
    project_name = os.getenv("COMPOSE_PROJECT_NAME")
    if not project_name:
        project_name = Path(compose_file).resolve().parent.name
    name_filter = f"{project_name}-"
    try:
        ps = runner(
            ["docker", "ps", "-aq", "--filter", f"name={name_filter}"],
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
