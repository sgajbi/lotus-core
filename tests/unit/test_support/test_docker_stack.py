"""Tests for bounded, diagnosable Docker Compose test-stack operation."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
import requests

from tests.test_support.docker_stack import (
    DockerImagePullFailureClass,
    DockerImagePullPolicy,
    DockerStackError,
    capture_compose_logs,
    compose_up,
    ensure_docker_engine_available,
    ensure_required_images_available,
    should_build_images,
    wait_for_compose_service_success,
    wait_for_http_health,
    wait_for_kafka_metadata,
    wait_for_migration_runner,
)
from tests.test_support.runtime_env import prepare_test_runtime


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


def test_compose_up_reallocates_reserved_ports_after_bind_race() -> None:
    runtime = prepare_test_runtime(
        profile="integration",
        scope="bind-race",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
    )
    attempted_query_ports: list[str] = []

    def runner(args, **kwargs):  # noqa: ANN001, ARG001
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=b"[]", stderr=b"")
        if "up" in args:
            attempted_query_ports.append(runtime.values["LOTUS_QUERY_HOST_PORT"])
            if len(attempted_query_ports) == 1:
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=args,
                    stderr=(b"failed to bind host port for 0.0.0.0:32001: address already in use"),
                )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    compose_up(
        "docker-compose.yml",
        build=False,
        retries=1,
        retry_wait_seconds=0,
        runner=runner,
        port_reservation=runtime.port_reservation,
    )

    assert len(attempted_query_ports) == 2
    assert attempted_query_ports[0] != attempted_query_ports[1]
    assert runtime.port_reservation.reserved_port_keys == ()


def test_compose_up_reports_exhausted_host_port_reallocation() -> None:
    runtime = prepare_test_runtime(
        profile="integration",
        scope="bind-race-exhausted",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
    )

    def runner(args, **kwargs):  # noqa: ANN001, ARG001
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=b"[]", stderr=b"")
        if "up" in args:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=args,
                stderr=b"Bind for 0.0.0.0:32001 failed: port is already allocated",
            )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    with pytest.raises(
        DockerStackError,
        match=("failure_class=host_port_bind_conflict, attempts=2, port_reallocations=1"),
    ):
        compose_up(
            "docker-compose.yml",
            build=False,
            retries=1,
            retry_wait_seconds=0,
            runner=runner,
            port_reservation=runtime.port_reservation,
        )

    runtime.port_reservation.release()


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

    pull_calls: list[list[str]] = []

    def runner(args, **kwargs):  # noqa: ANN001
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
        if args[0:2] == ["docker", "pull"]:
            pull_calls.append(list(args))
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=args,
                stderr=b"manifest unknown",
            )
        raise AssertionError(f"unexpected call: {args}")

    with pytest.raises(
        DockerStackError,
        match="failure_class=permanent, attempts=1",
    ):
        ensure_required_images_available(compose_file, runner)

    assert pull_calls == [["docker", "pull", "confluentinc/cp-zookeeper:7.5.0"]]


@pytest.mark.parametrize(
    "timeout_message",
    (
        b"context deadline exceeded",
        b"connect: connection timed out",
        b"Client.Timeout exceeded while awaiting headers",
    ),
)
def test_ensure_required_images_available_recovers_from_transient_timeout(
    monkeypatch: pytest.MonkeyPatch,
    timeout_message: bytes,
) -> None:
    monkeypatch.setattr(
        "tests.test_support.docker_stack._load_compose_pull_images",
        lambda _: ["prom/prometheus:v2.47.2"],
    )
    pull_timeouts: list[float] = []
    sleep_delays: list[float] = []

    def runner(args, **kwargs):  # noqa: ANN001
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
        if args[0:2] == ["docker", "pull"]:
            pull_timeouts.append(kwargs["timeout"])
            if len(pull_timeouts) == 1:
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=args,
                    stderr=timeout_message,
                )
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        raise AssertionError(f"unexpected call: {args}")

    ensure_required_images_available(
        "docker-compose.yml",
        runner,
        pull_policy=DockerImagePullPolicy(
            max_attempts=3,
            timeout_seconds=17,
            initial_backoff_seconds=2,
            jitter_ratio=0.25,
        ),
        sleeper=sleep_delays.append,
        jitter=lambda start, end: end,
    )

    assert pull_timeouts == [17, 17]
    assert sleep_delays == [2.5]


def test_ensure_required_images_available_bounds_timeout_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tests.test_support.docker_stack._load_compose_pull_images",
        lambda _: ["postgres:16-alpine"],
    )
    pull_attempts = 0

    def runner(args, **kwargs):  # noqa: ANN001
        nonlocal pull_attempts
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
        if args[0:2] == ["docker", "pull"]:
            pull_attempts += 1
            raise subprocess.TimeoutExpired(args, timeout=kwargs["timeout"])
        raise AssertionError(f"unexpected call: {args}")

    with pytest.raises(
        DockerStackError,
        match="failure_class=timeout, attempts=3",
    ):
        ensure_required_images_available(
            "docker-compose.yml",
            runner,
            pull_policy=DockerImagePullPolicy(
                max_attempts=3,
                timeout_seconds=5,
                initial_backoff_seconds=0,
            ),
            sleeper=lambda _: None,
        )

    assert pull_attempts == 3


def test_image_pull_policy_exposes_bounded_total_duration() -> None:
    policy = DockerImagePullPolicy(
        max_attempts=3,
        timeout_seconds=120,
        initial_backoff_seconds=2,
        max_backoff_seconds=15,
        jitter_ratio=0.20,
    )

    assert policy.maximum_total_duration_seconds == pytest.approx(367.2)


def test_image_pull_failure_classification_is_bounded_and_source_safe(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        "tests.test_support.docker_stack._load_compose_pull_images",
        lambda _: ["registry.example.test/platform/base:1"],
    )

    def runner(args, **kwargs):  # noqa: ANN001, ARG001
        if args[0:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args,
            stderr=b"unauthorized: https://auth.example.test/token?token=SECRET_VALUE",
        )

    with pytest.raises(DockerStackError) as exc_info:
        ensure_required_images_available("docker-compose.yml", runner)

    assert "SECRET_VALUE" not in str(exc_info.value)
    assert "SECRET_VALUE" not in caplog.text
    assert "failure_class=permanent" in str(exc_info.value)


@pytest.mark.parametrize(
    ("details", "expected"),
    [
        ("toomanyrequests: rate limit exceeded", DockerImagePullFailureClass.RATE_LIMITED),
        ("tls handshake timeout", DockerImagePullFailureClass.REGISTRY_UNAVAILABLE),
        ("connect: connection timed out", DockerImagePullFailureClass.REGISTRY_UNAVAILABLE),
        (
            "Client.Timeout exceeded while awaiting headers",
            DockerImagePullFailureClass.REGISTRY_UNAVAILABLE,
        ),
        ("manifest unknown", DockerImagePullFailureClass.PERMANENT),
    ],
)
def test_image_pull_failure_classification(
    details: str,
    expected: DockerImagePullFailureClass,
) -> None:
    from tests.test_support.docker_stack import _classify_image_pull_failure

    assert _classify_image_pull_failure(details) is expected


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


def test_wait_for_compose_service_success_accepts_zero_exit() -> None:
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(stdout="topic_creator_123\n"),
            SimpleNamespace(stdout="0\n"),
        ]
    )

    def runner(args, **kwargs):  # noqa: ANN001
        return next(responses)

    wait_for_compose_service_success(
        "docker-compose.yml",
        "kafka-topic-creator",
        timeout_seconds=1,
        poll_seconds=0,
        runner=runner,
    )


def test_wait_for_compose_service_success_raises_with_logs_on_non_zero_exit() -> None:
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(stdout="topic_creator_123\n"),
            SimpleNamespace(stdout="1\n"),
            SimpleNamespace(stdout="topic creation failed\n"),
        ]
    )

    def runner(args, **kwargs):  # noqa: ANN001
        return next(responses)

    with pytest.raises(DockerStackError, match="kafka-topic-creator exited"):
        wait_for_compose_service_success(
            "docker-compose.yml",
            "kafka-topic-creator",
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


def test_capture_compose_logs_writes_active_project_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls: list[list[str]] = []

    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "lotus-e2e-test")
    monkeypatch.setattr(
        "tests.test_support.docker_stack.ensure_docker_engine_available",
        lambda: None,
    )

    def runner(args, **kwargs):  # noqa: ANN001
        calls.append(list(args))
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return SimpleNamespace(stdout="service log\n", stderr="diagnostic stderr\n")

    monkeypatch.setattr("tests.test_support.docker_stack.subprocess.run", runner)

    output_path = tmp_path / "e2e-smoke" / "compose.log"
    capture_compose_logs("docker-compose.yml", output_path)

    assert calls == [
        [
            "docker",
            "compose",
            "-p",
            "lotus-e2e-test",
            "-f",
            "docker-compose.yml",
            "logs",
            "--no-color",
        ]
    ]
    assert output_path.read_text(encoding="utf-8") == (
        "service log\n\n--- docker compose logs stderr ---\ndiagnostic stderr\n"
    )
