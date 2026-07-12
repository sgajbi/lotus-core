"""Tests for managed, isolated Compose-backed validation runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_support.managed_compose_run import (
    ManagedComposeRun,
    prepare_managed_compose_run,
)


def test_prepare_managed_run_owns_unique_project_and_honors_local_endpoint_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "shared-project-must-not-leak")

    managed = prepare_managed_compose_run(
        scope="latency-gate",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres", "query-service"),
        build=False,
        log_path=tmp_path / "latency-compose.log",
        endpoint_urls={"E2E_QUERY_URL": "http://127.0.0.1:18401"},
    )

    try:
        assert managed.runtime.endpoints.compose_project_name.startswith("lotus-e2e-latency-gate-")
        assert managed.runtime.endpoints.compose_project_name != "shared-project-must-not-leak"
        assert managed.runtime.values["LOTUS_QUERY_HOST_PORT"] == "18401"
        assert "LOTUS_QUERY_HOST_PORT" not in managed.runtime.port_reservation.reserved_port_keys
    finally:
        managed.runtime.port_reservation.release()


def test_prepare_managed_run_does_not_inherit_parent_runtime_ports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOTUS_POSTGRES_HOST_PORT", "15432")

    managed = prepare_managed_compose_run(
        scope="fresh-ports",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres",),
        build=False,
        log_path=tmp_path / "fresh-ports.log",
    )

    try:
        assert managed.runtime.values["LOTUS_POSTGRES_HOST_PORT"] != "15432"
        assert "LOTUS_POSTGRES_HOST_PORT" in managed.runtime.port_reservation.reserved_port_keys
    finally:
        managed.runtime.port_reservation.release()


def test_prepare_managed_run_enables_demo_data_only_when_requested(tmp_path: Path) -> None:
    disabled = prepare_managed_compose_run(
        scope="without-seed-data",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres",),
        build=False,
        log_path=tmp_path / "without-seed-data.log",
    )
    enabled = prepare_managed_compose_run(
        scope="with-seed-data",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres", "demo_data_loader"),
        build=False,
        log_path=tmp_path / "with-seed-data.log",
        enable_demo_data_pack=True,
    )

    try:
        assert disabled.runtime.values["DEMO_DATA_PACK_ENABLED"] == "false"
        assert enabled.runtime.values["DEMO_DATA_PACK_ENABLED"] == "true"
    finally:
        disabled.runtime.port_reservation.release()
        enabled.runtime.port_reservation.release()


def test_managed_run_starts_with_exact_runtime_and_captures_before_teardown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[tuple[str, object]] = []
    managed = prepare_managed_compose_run(
        scope="docker-smoke",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres", "ingestion-service"),
        build=True,
        log_path=tmp_path / "diagnostics" / "docker-smoke-compose.log",
    )

    def fake_up(*args: object, **kwargs: object) -> None:
        events.append(("up", (args, kwargs)))

    def fake_capture(*args: object, **kwargs: object) -> None:
        events.append(("capture", (args, kwargs)))

    def fake_down(*args: object, **kwargs: object) -> None:
        events.append(("down", (args, kwargs)))

    monkeypatch.setattr("tests.test_support.managed_compose_run.compose_up", fake_up)
    monkeypatch.setattr("tests.test_support.managed_compose_run.capture_compose_logs", fake_capture)
    monkeypatch.setattr("tests.test_support.managed_compose_run.compose_down", fake_down)

    with managed:
        events.append(("body", managed.runtime.endpoints.compose_project_name))

    assert [name for name, _ in events] == ["up", "body", "capture", "down"]
    _, up_call = events[0]
    assert up_call[1]["runtime"] is managed.runtime
    assert up_call[1]["services"] == ["postgres", "ingestion-service"]
    assert up_call[1]["build"] is True
    _, capture_call = events[2]
    assert capture_call[1]["runtime"] is managed.runtime
    assert capture_call[0][1] == managed.log_path
    _, down_call = events[3]
    assert down_call[1]["runtime"] is managed.runtime


def test_managed_run_preserves_primary_error_when_diagnostics_and_teardown_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    managed = prepare_managed_compose_run(
        scope="performance-load",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres",),
        build=False,
        log_path=tmp_path / "performance-compose.log",
    )
    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.compose_up",
        lambda *args, **kwargs: None,
    )

    def fail_capture(*args: object, **kwargs: object) -> None:
        raise RuntimeError("diagnostic capture failed")

    def fail_down(*args: object, **kwargs: object) -> None:
        raise RuntimeError("teardown failed")

    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.capture_compose_logs",
        fail_capture,
    )
    monkeypatch.setattr("tests.test_support.managed_compose_run.compose_down", fail_down)

    with pytest.raises(ValueError, match="validation failed") as excinfo:
        with managed:
            raise ValueError("validation failed")

    notes = getattr(excinfo.value, "__notes__", [])
    assert any("diagnostic capture failed" in note for note in notes)
    assert any("teardown failed" in note for note in notes)


def test_managed_run_keep_stack_still_captures_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    managed = prepare_managed_compose_run(
        scope="local-debug",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres",),
        build=False,
        log_path=tmp_path / "local-debug-compose.log",
        keep_stack=True,
    )
    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.compose_up",
        lambda *args, **kwargs: calls.append("up"),
    )
    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.capture_compose_logs",
        lambda *args, **kwargs: calls.append("capture"),
    )
    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.compose_down",
        lambda *args, **kwargs: calls.append("down"),
    )

    with managed:
        pass

    assert calls == ["up", "capture"]
    assert managed.runtime.port_reservation.reserved_port_keys == ()


def test_startup_failure_captures_project_diagnostics_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    managed = prepare_managed_compose_run(
        scope="startup-failure",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres",),
        build=False,
        log_path=tmp_path / "startup-failure-compose.log",
    )

    def fail_up(*args: object, **kwargs: object) -> None:
        calls.append("up")
        raise RuntimeError("startup failed")

    monkeypatch.setattr("tests.test_support.managed_compose_run.compose_up", fail_up)
    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.capture_compose_logs",
        lambda *args, **kwargs: calls.append("capture"),
    )
    monkeypatch.setattr(
        "tests.test_support.managed_compose_run.compose_down",
        lambda *args, **kwargs: calls.append("down"),
    )

    with pytest.raises(RuntimeError, match="startup failed"):
        with managed:
            raise AssertionError("body must not execute")

    assert calls == ["up", "capture", "down"]


def test_managed_compose_run_type_is_context_manager() -> None:
    assert hasattr(ManagedComposeRun, "__enter__")
    assert hasattr(ManagedComposeRun, "__exit__")


def test_compose_command_is_bound_to_exact_file_and_project(tmp_path: Path) -> None:
    managed = prepare_managed_compose_run(
        scope="inspect",
        compose_file=tmp_path / "docker-compose.yml",
        services=("postgres",),
        build=False,
        log_path=tmp_path / "inspect.log",
    )

    try:
        assert managed.compose_command("ps", "-q", "postgres") == [
            "docker",
            "compose",
            "-f",
            managed.compose_file,
            "-p",
            managed.runtime.endpoints.compose_project_name,
            "ps",
            "-q",
            "postgres",
        ]
    finally:
        managed.runtime.port_reservation.release()
