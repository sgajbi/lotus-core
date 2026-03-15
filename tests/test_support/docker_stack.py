from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

import requests
import yaml
from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient


class DockerStackError(RuntimeError):
    """Raised when docker stack bring-up or health checks fail."""


def _compose_base_args(compose_file: str) -> list[str]:
    project_name = os.getenv("COMPOSE_PROJECT_NAME")
    args = ["docker", "compose"]
    if project_name:
        args.extend(["-p", project_name])
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
        try:
            runner(["docker", "pull", image], check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise DockerStackError(
                f"Failed to pull required Docker image '{image}': {details}"
            ) from exc


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
    ensure_docker_engine_available(runner)
    ensure_required_images_available(compose_file, runner)
    _remove_stale_project_containers(compose_file, runner)
    try:
        runner(
            [*_compose_base_args(compose_file), "down", "--remove-orphans"],
            check=False,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        # Best-effort cleanup only. Continue with bring-up retries.
        pass

    args = [*_compose_base_args(compose_file), "up"]
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
                        [*_compose_base_args(compose_file), "down", "--remove-orphans"],
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
    ensure_docker_engine_available(runner)
    start = time.time()
    while time.time() - start < timeout_seconds:
        result = runner(
            [*_compose_base_args(compose_file), "ps", "--status=exited", "-q", "migration-runner"],
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
            [*_compose_base_args(compose_file), "logs", "migration-runner"],
            capture_output=True,
            text=True,
            check=False,
        )
        raise DockerStackError(
            "migration-runner exited with non-zero status:\n" + logs_result.stdout
        )

    logs_result = runner(
        [*_compose_base_args(compose_file), "logs", "migration-runner"],
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


def compose_down(compose_file: str) -> None:
    ensure_docker_engine_available()
    subprocess.run(
        [*_compose_base_args(compose_file), "down", "-v", "--remove-orphans"],
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
    try:
        ps = runner(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project_name}"],
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
