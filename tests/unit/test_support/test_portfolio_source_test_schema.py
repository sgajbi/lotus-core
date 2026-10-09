"""No immutable test teardown reaches SQL without a current factory capability."""

import copy
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import make_url

from tests import conftest as harness
from tests.test_support import portfolio_source_observation_migration_dependencies as dependencies
from tests.test_support.db_cleanup import (
    DatabaseCleanupAuthorizationError,
    authorize_database_cleanup,
)
from tests.test_support.portfolio_source_test_schema import recreate_source_test_dependencies
from tests.test_support.runtime_env import prepare_test_runtime


@pytest.mark.parametrize("invalid", ["copied", "stale", "wrong-target", "unissued"])
def test_schema_reset_refuses_invalid_capability_before_sql(invalid):
    runtime = prepare_test_runtime(
        profile="integration",
        scope="cleanup-ownership",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    connection = MagicMock()
    connection.engine.url = make_url(runtime.endpoints.host_database_url)
    try:
        authorization = authorize_database_cleanup(runtime=runtime, engine=connection.engine)
        if invalid == "copied":
            authorization = copy.copy(authorization)
        elif invalid == "stale":
            runtime.port_reservation.reallocate()
            connection.engine.url = make_url(runtime.endpoints.host_database_url)
        elif invalid == "wrong-target":
            connection.engine.url = make_url("postgresql://user:password@localhost:5432/foreign")
        else:
            authorization = object()
        with pytest.raises(DatabaseCleanupAuthorizationError):
            with recreate_source_test_dependencies(connection, authorization=authorization):
                pytest.fail("invalid capability reached cleanup")
        connection.execute.assert_not_called()
        connection.scalar.assert_not_called()
    finally:
        runtime.port_reservation.release()


@pytest.mark.parametrize("invalid", ["live-target", "incomplete-or-unowned"])
def test_schema_reset_refuses_catalog_drift_before_destructive_sql(invalid):
    runtime = prepare_test_runtime(
        profile="integration",
        scope="cleanup-ownership",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    connection = MagicMock()
    connection.engine.url = make_url(runtime.endpoints.host_database_url)
    try:
        authorization = authorize_database_cleanup(runtime=runtime, engine=connection.engine)
        connection.execute.return_value.one.return_value = (
            authorization.target.database if invalid != "live-target" else "foreign",
            authorization.target.username,
        )
        connection.scalar.return_value = invalid != "incomplete-or-unowned"
        with pytest.raises(DatabaseCleanupAuthorizationError, match="incomplete or unowned"):
            with recreate_source_test_dependencies(connection, authorization=authorization):
                pytest.fail("catalog drift reached cleanup")
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        assert statements == ["SELECT current_database(), session_user"]
    finally:
        runtime.port_reservation.release()


@pytest.mark.parametrize("invalid", ["wrong-target", "stale"])
def test_historical_dependency_descent_refuses_before_migration(monkeypatch, invalid):
    runtime = prepare_test_runtime(
        profile="integration",
        scope="cleanup-ownership",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    connection = MagicMock()
    connection.engine.url = make_url(runtime.endpoints.host_database_url)
    migration = MagicMock()
    monkeypatch.setattr(harness, "_test_runtime", runtime)
    monkeypatch.setattr(dependencies, "fact_verification_migration", migration)
    try:
        if invalid == "wrong-target":
            connection.engine.url = make_url("postgresql://user:password@localhost:5432/foreign")
        else:
            runtime.values["POSTGRES_DB"] = "foreign"
        with pytest.raises(DatabaseCleanupAuthorizationError):
            dependencies.downgrade_observation_schema(connection)
        migration.assert_not_called()
        connection.execute.assert_not_called()
    finally:
        runtime.port_reservation.release()


def test_historical_restore_refuses_copied_capability_before_sql():
    runtime = prepare_test_runtime(
        profile="integration",
        scope="cleanup-ownership",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    connection = MagicMock()
    connection.engine.url = make_url(runtime.endpoints.host_database_url)
    try:
        authorization = authorize_database_cleanup(runtime=runtime, engine=connection.engine)
        with pytest.raises(
            DatabaseCleanupAuthorizationError, match="invalid cleanup authorization"
        ):
            dependencies.restore_observation_schema(
                {"_test_cleanup_authorization": copy.copy(authorization)}, connection
            )
        connection.execute.assert_not_called()
    finally:
        runtime.port_reservation.release()
