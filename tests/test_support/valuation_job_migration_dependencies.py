"""Descend through real valuation-job ownership before historical root cutovers."""

import runpy
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/c185b2c3d546_valuation_job_tenant_authority.py"
)
_TABLE = "portfolio_valuation_jobs"


def valuation_job_schema_semantics(connection: Connection) -> tuple:
    """Verify tenant authority and capture catalog definitions without transient OIDs."""
    inspector = inspect(connection)
    tenant = next(
        column for column in inspector.get_columns(_TABLE) if column["name"] == "tenant_id"
    )
    assert not tenant["nullable"] and str(tenant["type"]) == "VARCHAR(128)"
    foreign_keys = inspector.get_foreign_keys(_TABLE)
    owner_keys = [
        key for key in foreign_keys if key["name"] == "fk_portfolio_valuation_jobs_tenant_portfolio"
    ]
    assert len(owner_keys) == 1, "historical root cutover requires valuation-job owner authority"
    owner = owner_keys[0]
    assert owner["constrained_columns"] == ["tenant_id", "portfolio_id"]
    assert owner["referred_table"] == "portfolios"
    assert owner["referred_columns"] == ["tenant_id", "portfolio_id"]
    constraints = tuple(
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid), convalidated FROM pg_constraint "
                "WHERE conrelid = 'public.portfolio_valuation_jobs'::regclass ORDER BY conname"
            )
        )
    )
    assert all(row[2] for row in constraints)
    indexes = tuple(
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'portfolio_valuation_jobs' ORDER BY indexname"
            )
        )
    )
    return constraints, indexes


def downgrade_valuation_job_schema(connection: Connection) -> dict[str, Any]:
    """Historical tests require empty work and use the owning migration's real guards."""
    valuation_job_schema_semantics(connection)
    if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM portfolio_valuation_jobs LIMIT 1)")):
        raise AssertionError("historical root cutover requires empty valuation jobs")
    migration = runpy.run_path(str(_MIGRATION))
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations
    migration["downgrade"]()
    assert "tenant_id" not in {column["name"] for column in inspect(connection).get_columns(_TABLE)}
    return migration


def restore_valuation_job_schema(migration: dict[str, Any], connection: Connection) -> None:
    """Rebind actual migration operations when a lock test changes connections."""
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations
    migration["upgrade"]()
