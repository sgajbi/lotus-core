from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
import requests

from tests.test_support.docker_stack import (
    DockerStackError,
    compose_up,
    ensure_docker_engine_available,
    ensure_required_images_available,
    should_build_images,
    wait_for_http_health,
    wait_for_kafka_metadata,
    wait_for_migration_runner,
)


def test_should_build_images_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOTUS_TESTS_DOCKER_BUILD", raising=False)
    assert should_build_images() is False


def test_should_build_images_true_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOTUS_TESTS_DOCKER_BUILD", "true")
    assert should_build_images() is True


def test_ensure_docker_engine_available_raises_clear_error() -> None:
    def runner(args, **kwargs):  # noqa: ANN001, ARG001
        raise FileNotFoundError("docker not found")

    with pytest.raises(DockerStackError, match="Docker engine is not available"):
        ensure_docker_engine_available(runner)


def test_compose_up_retries_on_existing_image_conflict() -> None:
    calls: list[list[str]] = []

    def runner(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=b"[]", stderr=b"")
        if args[-2:] == ["up", "-d"] and len([c for c in calls if c[-2:] == ["up", "-d"]]) == 1:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=args,
                stderr=b'image "docker.io/library/lotus-core-query_service:latest": already exists',
            )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    compose_up(
        "docker-compose.yml",
        build=False,
        retries=1,
        retry_wait_seconds=0,
        runner=runner,
    )

    image_inspects = [call for call in calls if call[0:3] == ["docker", "image", "inspect"]]
    ps_calls = [call for call in calls if call[0:4] == ["docker", "ps", "-aq", "--filter"]]
    down_calls = [call for call in calls if call[-2:] == ["down", "--remove-orphans"]]
    up_calls = [call for call in calls if call[-2:] == ["up", "-d"]]

    assert calls[0][0:2] == ["docker", "info"]
    assert len(image_inspects) >= 2
    assert len(ps_calls) == 1
    assert len(down_calls) == 2
    assert len(up_calls) == 2


def test_compose_up_retries_on_migration_runner_exit() -> None:
    calls: list[list[str]] = []

    def runner(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=b"[]", stderr=b"")
        if args[-2:] == ["up", "-d"] and len([c for c in calls if c[-2:] == ["up", "-d"]]) == 1:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=args,
                stderr=b'service "migration-runner" didn\'t complete successfully: exit 255',
            )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    compose_up(
        "docker-compose.yml",
        build=False,
        retries=1,
        retry_wait_seconds=0,
        runner=runner,
    )

    image_inspects = [call for call in calls if call[0:3] == ["docker", "image", "inspect"]]
    ps_calls = [call for call in calls if call[0:4] == ["docker", "ps", "-aq", "--filter"]]
    down_calls = [call for call in calls if call[-2:] == ["down", "--remove-orphans"]]
    up_calls = [call for call in calls if call[-2:] == ["up", "-d"]]

    assert calls[0][0:2] == ["docker", "info"]
    assert len(image_inspects) >= 2
    assert len(ps_calls) == 1
    assert len(down_calls) == 2
    assert len(up_calls) == 2


def test_ensure_required_images_available_pulls_missing_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose_file = "docker-compose.yml"
    monkeypatch.setattr(
        "tests.test_support.docker_stack._load_compose_pull_images",
        lambda _: ["postgres:16-alpine", "confluentinc/cp-zookeeper:7.5.0"],
    )

    calls: list[list[str]] = []

    def runner(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(
                returncode=1 if args[-1] == "confluentinc/cp-zookeeper:7.5.0" else 0,
                stdout=b"",
                stderr=b"",
            )
        if args[0:2] == ["docker", "pull"]:
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        raise AssertionError(f"unexpected call: {args}")

    ensure_required_images_available(compose_file, runner)

    assert calls == [
        ["docker", "image", "inspect", "postgres:16-alpine"],
        ["docker", "image", "inspect", "confluentinc/cp-zookeeper:7.5.0"],
        ["docker", "pull", "confluentinc/cp-zookeeper:7.5.0"],
    ]


def test_ensure_required_images_available_raises_on_pull_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose_file = "docker-compose.yml"
    monkeypatch.setattr(
        "tests.test_support.docker_stack._load_compose_pull_images",
        lambda _: ["confluentinc/cp-zookeeper:7.5.0"],
    )

    def runner(args, **kwargs):  # noqa: ANN001
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
        if args[0:2] == ["docker", "pull"]:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=args,
                stderr=b"manifest unknown",
            )
        raise AssertionError(f"unexpected call: {args}")

    with pytest.raises(DockerStackError, match="Failed to pull required Docker image"):
        ensure_required_images_available(compose_file, runner)


def test_ensure_required_images_available_skips_repo_built_images(
    tmp_path,
) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        """
services:
  query-service:
    image: lotus-core/query-service:local
    build:
      context: .
      dockerfile: src/services/query_service/Dockerfile
  postgres:
    image: postgres:16-alpine
""".strip(),
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    def runner(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        raise AssertionError(f"unexpected call: {args}")

    ensure_required_images_available(str(compose_file), runner)

    assert calls == [["docker", "image", "inspect", "postgres:16-alpine"]]


def test_wait_for_migration_runner_success() -> None:
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(stdout="container123\n"),
            SimpleNamespace(stdout="0\n"),
        ]
    )

    def runner(args, **kwargs):  # noqa: ANN001
        return next(responses)

    wait_for_migration_runner(
        "docker-compose.yml",
        timeout_seconds=1,
        poll_seconds=0,
        runner=runner,
    )


def test_wait_for_http_health_raises_after_timeout() -> None:
    def always_fail(url: str, timeout: int):  # noqa: ARG001
        raise requests.ConnectionError("down")

    with pytest.raises(DockerStackError):
        wait_for_http_health(
            "query-service",
            "http://localhost:8201/health/ready",
            timeout_seconds=0,
            poll_seconds=0,
            get=always_fail,
        )


def test_wait_for_kafka_metadata_raises_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _AlwaysFailAdminClient:
        def __init__(self, conf):  # noqa: ANN001, ARG002
            pass

        def list_topics(self, timeout: int):  # noqa: ARG002
            raise Exception("not ready")

    monkeypatch.setattr("tests.test_support.docker_stack.AdminClient", _AlwaysFailAdminClient)

    with pytest.raises(DockerStackError, match="did not become metadata-ready"):
        wait_for_kafka_metadata("localhost:9092", timeout_seconds=0, poll_seconds=0)
