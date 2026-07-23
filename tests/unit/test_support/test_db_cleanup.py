from __future__ import annotations

import copy
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import Engine, make_url

from tests import conftest as root_conftest
from tests.test_support.db_cleanup import (
    DatabaseCleanupAuthorization,
    DatabaseCleanupAuthorizationError,
    authorize_database_cleanup,
    require_database_cleanup_authorization,
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


@pytest.mark.parametrize(
    "query",
    [
        "host=shared-postgres.internal",
        "port=5432",
        "options=-csearch_path%3Dshared",
        "search_path=shared",
    ],
)
def test_cleanup_rejects_connection_affecting_query_parameters(query: str) -> None:
    runtime = _runtime()
    engine = _engine(f"{runtime.endpoints.host_database_url}?{query}")
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="query parameters are not allowed",
        ) as raised:
            authorize_database_cleanup(runtime=runtime, engine=engine)
        assert query not in str(raised.value)
        assert "password" not in str(raised.value)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_cleanup_rejects_non_postgresql_backend() -> None:
    runtime = _runtime()
    target = runtime.prepared_database_target
    engine = _engine(f"mysql://user:password@{target.host}:{target.port}/{target.database}")
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="target backend must be PostgreSQL",
        ) as raised:
            authorize_database_cleanup(runtime=runtime, engine=engine)
        assert "password" not in str(raised.value)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_cleanup_rejects_post_preparation_endpoint_mutation_before_destructive_sql() -> None:
    runtime = _runtime()
    drifted_url = "postgresql://user:password@localhost:55432/portfolio_db"
    runtime.values["HOST_DATABASE_URL"] = drifted_url
    engine = _engine(drifted_url)
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="derived database endpoint changed after preparation",
        ) as raised:
            authorize_database_cleanup(runtime=runtime, engine=engine)
        assert "password" not in str(raised.value)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_cleanup_rejects_component_and_endpoint_mutation_before_destructive_sql() -> None:
    runtime = _runtime()
    drifted_url = "postgresql://user:password@localhost:55432/other_db"
    runtime.values["LOTUS_POSTGRES_HOST_PORT"] = "55432"
    runtime.values["POSTGRES_DB"] = "other_db"
    runtime.values["HOST_DATABASE_URL"] = drifted_url
    engine = _engine(drifted_url)
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="PostgreSQL target components changed after preparation",
        ) as raised:
            authorize_database_cleanup(runtime=runtime, engine=engine)
        assert "password" not in str(raised.value)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_cleanup_endpoint_mutation_never_leaks_malformed_credentials() -> None:
    runtime = _runtime()
    prepared_url = runtime.endpoints.host_database_url
    runtime.values["HOST_DATABASE_URL"] = "postgresql://user:supersecret@[bad-host/portfolio_db"
    engine = _engine(prepared_url)
    try:
        with pytest.raises(DatabaseCleanupAuthorizationError) as raised:
            authorize_database_cleanup(runtime=runtime, engine=engine)
        assert "supersecret" not in str(raised.value)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_cleanup_authorizes_target_refreshed_by_governed_port_reallocation() -> None:
    runtime = _runtime()
    first_target = runtime.prepared_database_target
    try:
        runtime.port_reservation.reallocate()
        refreshed_target = runtime.prepared_database_target
        engine = _engine(runtime.endpoints.host_database_url)

        authorization = authorize_database_cleanup(runtime=runtime, engine=engine)

        assert refreshed_target is not first_target
        assert refreshed_target.port != first_target.port
        assert refreshed_target.reservation_generation == 2
        assert refreshed_target.port == int(
            runtime.port_reservation._sockets["LOTUS_POSTGRES_HOST_PORT"].getsockname()[1]
        )
        assert authorization.target.port == refreshed_target.port
        require_database_cleanup_authorization(authorization, engine=engine)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_target_evidence_cannot_refresh_without_new_reservation_generation() -> None:
    runtime = _runtime()
    prepared = runtime.prepared_database_target
    runtime.values["LOTUS_POSTGRES_HOST_PORT"] = "55432"
    runtime.values["HOST_DATABASE_URL"] = "postgresql://user:password@localhost:55432/portfolio_db"
    try:
        with pytest.raises(AttributeError):
            runtime.port_reservation.generation = runtime.port_reservation.generation + 1
        with pytest.raises(
            RuntimeError,
            match="requires a newer reservation generation",
        ):
            runtime.port_reservation._refresh_prepared_database_target_for_reallocation()
        assert runtime.prepared_database_target is prepared
        engine = _engine(runtime.values["HOST_DATABASE_URL"])
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="PostgreSQL target components changed after preparation",
        ):
            authorize_database_cleanup(runtime=runtime, engine=engine)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_target_evidence_refresh_requires_active_owned_postgresql_socket() -> None:
    runtime = _runtime()
    runtime.port_reservation.release()
    runtime.port_reservation._generation += 1
    runtime.port_reservation._active_reservation_epoch = object()
    with pytest.raises(
        RuntimeError,
        match="active owned reservation for LOTUS_POSTGRES_HOST_PORT",
    ):
        runtime.port_reservation._refresh_prepared_database_target_for_reallocation()


def test_cleanup_authorizes_generated_project_owned_port_and_exact_engine() -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)
    try:
        authorization = authorize_database_cleanup(runtime=runtime, engine=engine)
        assert authorization.compose_project_name == runtime.endpoints.compose_project_name
        assert authorization.target.port == int(runtime.values["LOTUS_POSTGRES_HOST_PORT"])
    finally:
        runtime.port_reservation.release()


def test_delegated_cleanup_rejects_authorization_from_retired_reservation_generation() -> None:
    runtime = _runtime()
    retired_engine = _engine(runtime.endpoints.host_database_url)
    authorization = authorize_database_cleanup(runtime=runtime, engine=retired_engine)
    try:
        runtime.port_reservation.reallocate()

        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="stale for the current runtime generation or target",
        ):
            require_database_cleanup_authorization(
                authorization,
                engine=retired_engine,
            )
        assert not retired_engine.begin.called
    finally:
        runtime.port_reservation.release()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"COMPOSE_PROJECT_NAME": "lotus-shared"}, "Compose project identity changed"),
        ({"POSTGRES_DB": "shared"}, "PostgreSQL target components changed"),
        (
            {"HOST_DATABASE_URL": "postgresql://user:password@localhost:55432/shared"},
            "derived database endpoint changed",
        ),
    ],
)
def test_delegated_cleanup_revalidates_runtime_drift_after_issuance(
    mutation: dict[str, str],
    message: str,
) -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)
    authorization = authorize_database_cleanup(runtime=runtime, engine=engine)
    runtime.values.update(mutation)
    try:
        with pytest.raises(DatabaseCleanupAuthorizationError, match=message):
            require_database_cleanup_authorization(authorization, engine=engine)
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_delegated_cleanup_rejects_copied_capability_before_destructive_sql() -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)
    try:
        authorization = authorize_database_cleanup(runtime=runtime, engine=engine)
        copied_authorization = copy.copy(authorization)
        assert copied_authorization is not authorization
        assert not hasattr(authorization, "_authority")
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="invalid cleanup authorization",
        ):
            require_database_cleanup_authorization(
                copied_authorization,
                engine=engine,
            )
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_cleanup_authorization_cannot_be_constructed_by_a_caller() -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)
    try:
        issued = authorize_database_cleanup(runtime=runtime, engine=engine)
        with pytest.raises(TypeError, match="factory-issued"):
            DatabaseCleanupAuthorization(
                compose_project_name="lotus-shared",
                target=issued.target,
                _issuance_token=object(),
            )
    finally:
        runtime.port_reservation.release()


def test_function_cleanup_refuses_before_destructive_cleanup(
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


def test_module_cleanup_refuses_before_quiescence_or_destructive_cleanup(
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


def test_function_cleanup_revalidates_authority_immediately_before_truncate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)
    real_authorize = root_conftest.authorize_database_cleanup

    def _authorize_then_drift(
        *, runtime: PreparedTestRuntime, engine: Engine
    ) -> DatabaseCleanupAuthorization:
        authorization = real_authorize(runtime=runtime, engine=engine)
        runtime.values["COMPOSE_PROJECT_NAME"] = "lotus-shared"
        return authorization

    monkeypatch.setattr(root_conftest, "_test_runtime", runtime)
    monkeypatch.setattr(root_conftest, "authorize_database_cleanup", _authorize_then_drift)
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="Compose project identity changed",
        ):
            next(root_conftest.clean_db.__wrapped__(engine))
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_module_cleanup_revalidates_authority_after_quiescence_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    engine = _engine(runtime.endpoints.host_database_url)

    def _wait_then_drift(
        db_engine: Engine,
        *,
        scope_label: str,
        cleanup_authorization: DatabaseCleanupAuthorization,
    ) -> None:
        del db_engine, scope_label, cleanup_authorization
        runtime.values["POSTGRES_DB"] = "shared"

    monkeypatch.setattr(root_conftest, "_test_runtime", runtime)
    monkeypatch.setattr(
        root_conftest,
        "_wait_for_pipeline_idle_with_recovery",
        _wait_then_drift,
    )
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="PostgreSQL target components changed",
        ):
            next(root_conftest.clean_db_module.__wrapped__(engine))
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
