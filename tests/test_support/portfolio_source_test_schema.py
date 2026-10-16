"""Capability-checked lifecycle for immutable source dependencies in owned test DBs.

This is schema teardown/recreation, not a production mutation or migration downgrade.
The caller's transaction also contains parent cleanup; failure rolls everything back.
"""

import runpy
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import Connection

from tests.test_support.db_cleanup import (
    DatabaseCleanupAuthorization,
    DatabaseCleanupAuthorizationError,
    require_database_cleanup_authorization,
)

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic/versions"
_TABLES = (
    "portfolio_financial_source_capture_links",
    "portfolio_financial_source_capture_segments",
    "portfolio_financial_source_cut_work",
    "portfolio_financial_source_cut_heads",
    "portfolio_financial_source_cut_inputs",
    "portfolio_historical_registry_members",
    "portfolio_financial_source_cut_chunks",
    "portfolio_financial_source_captures",
    "portfolio_financial_source_cut_manifests",
    "portfolio_flow_source_cuts",
    "portfolio_flow_event_observation_heads",
    "portfolio_flow_event_observations",
    "portfolio_source_fact_verifications",
    "portfolio_cash_availability_observation_heads",
    "portfolio_funding_investment_observation_heads",
    "portfolio_cash_availability_observations",
    "portfolio_funding_investment_observations",
)
_FUNCTIONS = (
    "refuse_source_fact_verification_mutation",
    "reject_portfolio_source_observation_mutation",
    "guard_empty_portfolio_source_observation_truncate",
)


def fact_verification_migration(connection: Connection) -> dict:
    """Bind the actual receipt migration to the caller's selected owned namespace."""
    module = runpy.run_path(
        str(_VERSIONS / "c181b2c3d542_add_portfolio_source_fact_verifications.py")
    )
    assert module["revision"] == "c181b2c3d542"
    assert module["down_revision"] == "c179b2c3d540"
    module["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    return module


def flow_observation_migration(connection: Connection) -> dict:
    """Bind the real flow migration, retaining its empty-history downgrade guards."""
    module = runpy.run_path(str(_VERSIONS / "c187b2c3d548_portfolio_flow_source_observations.py"))
    assert module["revision"] == "c187b2c3d548"
    assert module["down_revision"] == "c186b2c3d547"
    module["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    return module


def financial_source_cut_migration(connection: Connection) -> dict:
    """Replay only the frozen neutral custody DDL on the capability-owned namespace."""
    module = runpy.run_path(str(_VERSIONS / "c188b2c3d549_portfolio_financial_source_cuts.py"))
    assert module["revision"] == "c188b2c3d549"
    assert module["down_revision"] == "c187b2c3d548"
    module["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    return module


@contextmanager
def recreate_source_test_dependencies(
    connection: Connection, *, authorization: DatabaseCleanupAuthorization
) -> Iterator[None]:
    """Reset only the seventeen source tables on an exact factory-owned test target.

    No CASCADE on DDL: an unknown dependent object refuses teardown. Recreate from
    frozen real migrations, including original foreign keys, indexes and triggers.
    Never call this from production, or use it to claim downgrade support.
    """
    require_database_cleanup_authorization(authorization, engine=connection.engine)
    identity = connection.execute(text("SELECT current_database(), session_user")).one()
    owned = connection.scalar(
        text(
            "SELECT count(*) = :table_count "
            "AND bool_and(pg_get_userbyid(c.relowner) = session_user) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r' AND c.relname = ANY(:tables)"
        ),
        {"tables": list(_TABLES), "table_count": len(_TABLES)},
    )
    if (
        tuple(identity) != (authorization.target.database, authorization.target.username)
        or not owned
    ):
        raise DatabaseCleanupAuthorizationError(
            "source test schema reset refused: incomplete or unowned migrated dependency"
        )
    require_database_cleanup_authorization(authorization, engine=connection.engine)
    connection.execute(text("SET LOCAL search_path TO public, pg_temp"))
    for table in _TABLES:
        require_database_cleanup_authorization(authorization, engine=connection.engine)
        connection.execute(text(f"DROP TABLE public.{table}"))
    for function in _FUNCTIONS:
        require_database_cleanup_authorization(authorization, engine=connection.engine)
        connection.execute(text(f"DROP FUNCTION public.{function}()"))
    yield
    require_database_cleanup_authorization(authorization, engine=connection.engine)
    observations = runpy.run_path(
        str(_VERSIONS / "c178b2c3d539_add_portfolio_source_observations.py")
    )
    observations["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    observations["upgrade"]()
    require_database_cleanup_authorization(authorization, engine=connection.engine)
    fact_verification_migration(connection)["upgrade"]()
    require_database_cleanup_authorization(authorization, engine=connection.engine)
    flow_observation_migration(connection)["upgrade"]()
    require_database_cleanup_authorization(authorization, engine=connection.engine)
    financial_source_cut_migration(connection)["upgrade"]()
