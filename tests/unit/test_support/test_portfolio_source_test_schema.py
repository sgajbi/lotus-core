"""No immutable test teardown reaches SQL without a current factory capability."""

import copy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import make_url

from tests import conftest as harness
from tests.test_support import portfolio_source_observation_migration_dependencies as dependencies
from tests.test_support import portfolio_source_test_schema as source_schema
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
    monkeypatch.setattr(dependencies, "financial_source_cut_migration", migration)
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


def test_complete_owned_reset_recreates_real_migration_order(monkeypatch):
    runtime = prepare_test_runtime(
        profile="integration",
        scope="cleanup-ownership",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    connection = MagicMock()
    connection.engine.url = make_url(runtime.endpoints.host_database_url)
    migrated = []

    def migration(path):
        revision = Path(path).name.split("_")[0]

        def upgrade():
            migrated.append(revision)

        return {
            "revision": revision,
            "down_revision": {"c181b2c3d542": "c179b2c3d540", "c188b2c3d549": "c187b2c3d548"}.get(
                revision, "c186b2c3d547"
            ),
            "upgrade": upgrade,
        }

    monkeypatch.setattr(source_schema.runpy, "run_path", migration)
    monkeypatch.setattr(source_schema.MigrationContext, "configure", lambda _: MagicMock())
    monkeypatch.setattr(source_schema, "Operations", lambda _: MagicMock())
    try:
        authorization = authorize_database_cleanup(runtime=runtime, engine=connection.engine)
        connection.execute.return_value.one.return_value = (
            authorization.target.database,
            authorization.target.username,
        )
        connection.scalar.return_value = True
        with recreate_source_test_dependencies(connection, authorization=authorization):
            assert migrated == []
        assert migrated == ["c178b2c3d539", "c181b2c3d542", "c187b2c3d548", "c188b2c3d549"]
        tables = connection.scalar.call_args.args[1]
        assert tables["table_count"] == len(tables["tables"]) == 17
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        drops = [sql for sql in statements if sql.startswith("DROP TABLE")]
        assert drops[9:12] == [
            "DROP TABLE public.portfolio_flow_source_cuts",
            "DROP TABLE public.portfolio_flow_event_observation_heads",
            "DROP TABLE public.portfolio_flow_event_observations",
        ]
        assert len(drops) == 17
        assert drops[:9] == ["DROP TABLE public." + name for name in source_schema._TABLES[:9]]
        assert not any("CASCADE" in sql for sql in statements)
        assert statements.index(drops[-1]) < next(
            i for i, sql in enumerate(statements) if sql.startswith("DROP FUNCTION")
        )
    finally:
        runtime.port_reservation.release()


def test_schema_reset_rechecks_capability_after_catalog_read():
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
            authorization.target.database,
            authorization.target.username,
        )

        def expire_after_catalog(*args):
            runtime.port_reservation.reallocate()
            return True

        connection.scalar.side_effect = expire_after_catalog
        with pytest.raises(DatabaseCleanupAuthorizationError):
            with recreate_source_test_dependencies(connection, authorization=authorization):
                pytest.fail("expired capability reached cleanup")
        assert [str(call.args[0]) for call in connection.execute.call_args_list] == [
            "SELECT current_database(), session_user"
        ]
    finally:
        runtime.port_reservation.release()


def test_historical_descent_and_restore_order_preserves_flow_guard(monkeypatch):
    runtime = prepare_test_runtime(
        profile="integration",
        scope="cleanup-ownership",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    connection = MagicMock()
    connection.engine.url = make_url(runtime.endpoints.host_database_url)
    actions = []

    def module(name):
        def upgrade():
            actions.append((name, "upgrade"))

        def downgrade():
            actions.append((name, "downgrade"))

        return {"upgrade": upgrade, "downgrade": downgrade}

    monkeypatch.setattr(harness, "_test_runtime", runtime)
    monkeypatch.setattr(dependencies, "flow_observation_migration", lambda _: module("flow"))
    monkeypatch.setattr(dependencies, "financial_source_cut_migration", lambda _: module("neutral"))
    monkeypatch.setattr(dependencies, "fact_verification_migration", lambda _: module("receipt"))
    monkeypatch.setattr(dependencies.runpy, "run_path", lambda _: module("observation"))
    monkeypatch.setattr(dependencies.MigrationContext, "configure", lambda _: MagicMock())
    monkeypatch.setattr(dependencies, "Operations", lambda _: MagicMock())
    try:
        migration = dependencies.downgrade_observation_schema(connection)
        dependencies.restore_observation_schema(migration, connection)
        assert actions == [
            ("neutral", "downgrade"),
            ("flow", "downgrade"),
            ("receipt", "downgrade"),
            ("observation", "downgrade"),
            ("observation", "upgrade"),
            ("receipt", "upgrade"),
            ("flow", "upgrade"),
            ("neutral", "upgrade"),
        ]
        actions.clear()

        def refuse_nonempty(_):
            result = module("flow")

            def refuse():
                raise RuntimeError("nonempty flow source history cannot be downgraded")

            result["downgrade"] = refuse
            return result

        monkeypatch.setattr(dependencies, "flow_observation_migration", refuse_nonempty)
        with pytest.raises(RuntimeError, match="nonempty flow"):
            dependencies.downgrade_observation_schema(connection)
        assert actions == [("neutral", "downgrade")]
        actions.clear()

        def refuse_neutral(_):
            result = module("neutral")

            def refuse():
                raise RuntimeError("nonempty neutral source custody cannot be downgraded")

            result["downgrade"] = refuse
            return result

        monkeypatch.setattr(dependencies, "financial_source_cut_migration", refuse_neutral)
        with pytest.raises(RuntimeError, match="nonempty neutral"):
            dependencies.downgrade_observation_schema(connection)
        assert actions == []
    finally:
        runtime.port_reservation.release()
