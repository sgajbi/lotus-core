from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import make_url

from tests import conftest as root_conftest
from tests.test_support.db_cleanup import (
    DatabaseCleanupAuthorizationError,
    authorize_database_cleanup,
    truncate_with_deadlock_retry,
)
from tests.test_support.runtime_env import PreparedTestRuntime, prepare_test_runtime


def _runtime(
    *,
    env: dict[str, str] | None = None,
    preserve_existing: bool = False,
) -> PreparedTestRuntime:
    return prepare_test_runtime(
        profile="integration",
        scope="cleanup-ownership",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true", **(env or {})},
        preserve_existing=preserve_existing,
        inherit_process_environment=False,
    )


def _engine(database_url: str) -> MagicMock:
    engine = MagicMock()
    engine.url = make_url(database_url)
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = []
    return engine


def _consume_fixture(generator: Iterator[None]) -> None:
    next(generator)
    with pytest.raises(StopIteration):
        next(generator)


def test_truncate_with_deadlock_retry_retries_then_succeeds() -> None:
    state = {"calls": 0}

    def flaky() -> None:
        state["calls"] += 1
        if state["calls"] < 3:
            raise RuntimeError("deadlock detected while truncating")

    truncate_with_deadlock_retry(flaky, max_attempts=4, backoff_seconds=0)
    assert state["calls"] == 3


def test_truncate_with_deadlock_retry_raises_non_deadlock() -> None:
    def hard_fail() -> None:
        raise RuntimeError("permission denied")

    with pytest.raises(RuntimeError, match="permission denied"):
        truncate_with_deadlock_retry(hard_fail, max_attempts=4, backoff_seconds=0)


@pytest.mark.parametrize(
    ("env", "message"),
    [
        (
            {"COMPOSE_PROJECT_NAME": "lotus-core-app-local"},
            "Compose project identity was inherited",
        ),
        (
            {"COMPOSE_PROJECT_NAME": "lotus-integration-cleanup-ownership-forged"},
            "Compose project identity was inherited",
        ),
        (
            {"LOTUS_POSTGRES_HOST_PORT": "55432"},
            "PostgreSQL host port was not dynamically reserved",
        ),
        (
            {
                "COMPOSE_PROJECT_NAME": "lotus-shared-test",
                "LOTUS_POSTGRES_HOST_PORT": "55432",
            },
            "Compose project identity was inherited",
        ),
    ],
)
def test_cleanup_rejects_inherited_or_forged_runtime_identity(
    env: dict[str, str],
    message: str,
) -> None:
    runtime = _runtime(env=env, preserve_existing=True)
    engine = _engine(runtime.endpoints.host_database_url)
    try:
        with pytest.raises(DatabaseCleanupAuthorizationError, match=message):
            authorize_database_cleanup(runtime=runtime, engine=engine)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


@pytest.mark.parametrize(
    "drifted_url",
    [
        "postgresql://user:password@localhost:55432/portfolio_db",
        "postgresql://user:password@localhost:55433/other_db",
    ],
)
def test_cleanup_rejects_actual_engine_target_drift(drifted_url: str) -> None:
    runtime = _runtime()
    engine = _engine(drifted_url)
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="engine target does not match prepared test runtime",
        ) as raised:
            authorize_database_cleanup(runtime=runtime, engine=engine)
        assert "password" not in str(raised.value)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_cleanup_authorizes_generated_project_owned_port_and_exact_engine() -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)
    try:
        authorization = authorize_database_cleanup(runtime=runtime, engine=engine)
        assert authorization.compose_project_name == runtime.endpoints.compose_project_name
        assert authorization.target.port == int(runtime.values["LOTUS_POSTGRES_HOST_PORT"])
    finally:
        runtime.port_reservation.release()


def test_function_cleanup_refuses_before_session_termination_or_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(
        env={"COMPOSE_PROJECT_NAME": "lotus-core-app-local"},
        preserve_existing=True,
    )
    engine = _engine(runtime.endpoints.host_database_url)
    monkeypatch.setattr(root_conftest, "_test_runtime", runtime)
    monkeypatch.setenv("LOTUS_TESTS_TERMINATE_DB_SESSIONS", "true")
    try:
        with pytest.raises(DatabaseCleanupAuthorizationError):
            next(root_conftest.clean_db.__wrapped__(engine))
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_module_cleanup_refuses_before_quiescence_recovery_or_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(
        env={"COMPOSE_PROJECT_NAME": "lotus-core-app-local"},
        preserve_existing=True,
    )
    engine = _engine(runtime.endpoints.host_database_url)
    waited = MagicMock()
    monkeypatch.setattr(root_conftest, "_test_runtime", runtime)
    monkeypatch.setattr(root_conftest, "_wait_for_pipeline_idle_with_recovery", waited)
    try:
        with pytest.raises(DatabaseCleanupAuthorizationError):
            next(root_conftest.clean_db_module.__wrapped__(engine))
        waited.assert_not_called()
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_function_cleanup_accepts_owned_exact_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)
    monkeypatch.setattr(root_conftest, "_test_runtime", runtime)
    try:
        _consume_fixture(root_conftest.clean_db.__wrapped__(engine))
        assert engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_module_cleanup_accepts_owned_exact_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)
    waited = MagicMock()
    monkeypatch.setattr(root_conftest, "_test_runtime", runtime)
    monkeypatch.setattr(root_conftest, "_wait_for_pipeline_idle_with_recovery", waited)
    try:
        _consume_fixture(root_conftest.clean_db_module.__wrapped__(engine))
        waited.assert_called_once()
        assert engine.begin.called
    finally:
        runtime.port_reservation.release()
