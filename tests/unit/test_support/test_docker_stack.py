from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
import requests

from tests.test_support.docker_stack import (
    DockerStackError,
    compose_up,
    should_build_images,
    wait_for_http_health,
    wait_for_migration_runner,
)


def test_should_build_images_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOTUS_TESTS_DOCKER_BUILD", raising=False)
    assert should_build_images() is False


def test_should_build_images_true_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOTUS_TESTS_DOCKER_BUILD", "true")
    assert should_build_images() is True


def test_compose_up_retries_on_existing_image_conflict() -> None:
    calls: list[list[str]] = []

    def runner(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
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

    assert calls[0][-2:] == ["down", "--remove-orphans"]
    assert calls[1][-2:] == ["up", "-d"]
    assert calls[2][-2:] == ["down", "--remove-orphans"]
    assert calls[3][-2:] == ["up", "-d"]


def test_compose_up_retries_on_migration_runner_exit() -> None:
    calls: list[list[str]] = []

    def runner(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
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

    assert calls[0][-2:] == ["down", "--remove-orphans"]
    assert calls[1][-2:] == ["up", "-d"]
    assert calls[2][-2:] == ["down", "--remove-orphans"]
    assert calls[3][-2:] == ["up", "-d"]


def test_wait_for_migration_runner_success() -> None:
    responses = iter(
        [
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
