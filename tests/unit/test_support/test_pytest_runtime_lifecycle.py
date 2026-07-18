"""Tests for process-owned pytest runtime reservation cleanup."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, cast

import pytest

import tests.conftest as root_conftest
from tests.test_support.runtime_env import PreparedTestRuntime, prepare_test_runtime


def _prepared_runtime(scope: str) -> PreparedTestRuntime:
    return prepare_test_runtime(
        profile="unit",
        scope=scope,
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )


def test_unit_only_session_finish_releases_all_runtime_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _prepared_runtime("unit-only-cleanup")
    monkeypatch.setattr(root_conftest, "_test_runtime", runtime)

    try:
        assert runtime.port_reservation.reserved_port_keys

        root_conftest.pytest_sessionfinish(
            cast(pytest.Session, object()),
            0,
        )

        assert runtime.port_reservation.reserved_port_keys == ()
    finally:
        runtime.port_reservation.release()


def test_docker_fixture_and_session_finish_share_idempotent_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _prepared_runtime("fixture-cleanup")
    compose_down_calls: list[PreparedTestRuntime] = []
    monkeypatch.setattr(root_conftest, "_test_runtime", runtime)
    monkeypatch.setenv("LOTUS_TEST_SCOPE", "unit-db")
    monkeypatch.delenv("LOTUS_TESTS_KEEP_STACK_UP", raising=False)
    monkeypatch.setattr(root_conftest, "resolve_compose_file", lambda _root: "compose.yml")
    monkeypatch.setattr(root_conftest, "should_build_images", lambda: False)
    monkeypatch.setattr(root_conftest, "compose_up", lambda *args, **kwargs: None)
    monkeypatch.setattr(root_conftest, "wait_for_migration_runner", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        root_conftest,
        "compose_down",
        lambda _compose_file, *, runtime: compose_down_calls.append(runtime),
    )

    fixture_owner: Generator[None, Any, None] = root_conftest.docker_services.__wrapped__(None)
    try:
        next(fixture_owner)
        with pytest.raises(StopIteration):
            next(fixture_owner)

        assert runtime.port_reservation.reserved_port_keys == ()
        assert compose_down_calls == [runtime]

        root_conftest.pytest_sessionfinish(
            cast(pytest.Session, object()),
            0,
        )
        assert runtime.port_reservation.reserved_port_keys == ()
    finally:
        fixture_owner.close()
        runtime.port_reservation.release()
