"""Real-PostgreSQL proof for simulation-session tenant ownership cutover."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c166b2c3d52d_fix_bind_simulation_session_tenant.py"
)
SUCCESSOR = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c167b2c3d52e_fix_bind_analytics_export_job_tenant.py"
)
RECONCILIATION_SUCCESSOR = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c168b2c3d52f_fix_bind_financial_reconciliation_tenant.py"
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


@pytest.mark.usefixtures("clean_db")
def test_simulation_session_tenant_cutover_backfills_and_enforces_portfolio_owner(
    db_engine,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    successor: dict[str, Any] = runpy.run_path(str(SUCCESSOR))
    reconciliation_successor: dict[str, Any] = runpy.run_path(str(RECONCILIATION_SUCCESSOR))

    with db_engine.connect() as connection:
        _bind_operations(migration, connection)
        _bind_operations(successor, connection)
        _bind_operations(reconciliation_successor, connection)
        connection.rollback()
        transaction = connection.begin()
        try:
            reconciliation_columns = {
                column["name"]
                for column in inspect(connection).get_columns("financial_reconciliation_runs")
            }
            if "tenant_id" in reconciliation_columns:
                reconciliation_successor["downgrade"]()

            analytics_export_columns = {
                column["name"]
                for column in inspect(connection).get_columns("analytics_export_jobs")
            }
            if "tenant_id" in analytics_export_columns:
                successor["downgrade"]()

            columns = {
                column["name"] for column in inspect(connection).get_columns("simulation_sessions")
            }
            if "tenant_id" in columns:
                migration["downgrade"]()

            connection.execute(
                text(
                    """
                    INSERT INTO portfolios (
                        portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                        risk_exposure, investment_time_horizon, portfolio_type,
                        booking_center_code, client_id, is_leverage_allowed, status
                    ) VALUES (
                        'PORT-MIGRATION-B', 'tenant-b', 'BOOK-B', 'USD', DATE '2026-01-01',
                        'balanced', 'long_term', 'discretionary', 'SG', 'CLIENT-B', FALSE, 'ACTIVE'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO simulation_sessions (
                        session_id, portfolio_id, status, version, created_by, expires_at
                    ) VALUES (
                        'SESSION-LEGACY-B', 'PORT-MIGRATION-B', 'ACTIVE', 1,
                        'legacy-user', TIMESTAMPTZ '2026-09-01 00:00:00+00'
                    )
                    """
                )
            )

            migration["upgrade"]()

            assert (
                connection.execute(
                    text(
                        "SELECT tenant_id FROM simulation_sessions "
                        "WHERE session_id = 'SESSION-LEGACY-B'"
                    )
                ).scalar_one()
                == "tenant-b"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT session_id FROM simulation_sessions "
                        "WHERE tenant_id = 'tenant-a' AND session_id = 'SESSION-LEGACY-B'"
                    )
                ).scalar_one_or_none()
                is None
            )
            foreign_update = connection.execute(
                text(
                    "UPDATE simulation_sessions SET status = 'CLOSED', version = 2 "
                    "WHERE tenant_id = 'tenant-a' AND session_id = 'SESSION-LEGACY-B'"
                )
            )
            assert foreign_update.rowcount == 0
            assert (
                connection.execute(
                    text(
                        "SELECT status FROM simulation_sessions "
                        "WHERE tenant_id = 'tenant-b' AND session_id = 'SESSION-LEGACY-B'"
                    )
                ).scalar_one()
                == "ACTIVE"
            )

            invalid_insert = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO simulation_sessions (
                            session_id, tenant_id, portfolio_id, status, version,
                            created_by, expires_at
                        ) VALUES (
                            'SESSION-FORGED-A', 'tenant-a', 'PORT-MIGRATION-B', 'ACTIVE', 1,
                            'forged-user', TIMESTAMPTZ '2026-09-01 00:00:00+00'
                        )
                        """
                    )
                )
            invalid_insert.rollback()

            migration["downgrade"]()
            columns = {
                column["name"] for column in inspect(connection).get_columns("simulation_sessions")
            }
            assert "tenant_id" not in columns
        finally:
            transaction.rollback()
