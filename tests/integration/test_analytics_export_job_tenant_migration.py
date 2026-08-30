"""Real-PostgreSQL proof for analytics-export tenant ownership cutover."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c167b2c3d52e_fix_bind_analytics_export_job_tenant.py"
)
PREDECESSOR = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c166b2c3d52d_fix_bind_simulation_session_tenant.py"
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


@pytest.mark.usefixtures("clean_db")
def test_analytics_export_cutover_backfills_and_enforces_portfolio_owner(db_engine) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    predecessor: dict[str, Any] = runpy.run_path(str(PREDECESSOR))

    with db_engine.connect() as connection:
        _bind_operations(migration, connection)
        _bind_operations(predecessor, connection)
        connection.rollback()
        transaction = connection.begin()
        try:
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("analytics_export_jobs")
            }
            if "tenant_id" in columns:
                migration["downgrade"]()

            simulation_columns = {
                column["name"] for column in inspect(connection).get_columns("simulation_sessions")
            }
            if "tenant_id" not in simulation_columns:
                predecessor["upgrade"]()

            connection.execute(
                text(
                    """
                    INSERT INTO portfolios (
                        portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                        risk_exposure, investment_time_horizon, portfolio_type,
                        booking_center_code, client_id, is_leverage_allowed, status
                    ) VALUES (
                        'PORT-EXPORT-B', 'tenant-b', 'BOOK-B', 'USD', DATE '2026-01-01',
                        'balanced', 'long_term', 'discretionary', 'SG', 'CLIENT-B', FALSE, 'ACTIVE'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO analytics_export_jobs (
                        job_id, dataset_type, portfolio_id, status, request_fingerprint,
                        request_payload, result_format, compression
                    ) VALUES (
                        'aexp_legacy_b', 'positions', 'PORT-EXPORT-B', 'completed',
                        'shared-fingerprint', '{}'::json, 'json', 'none'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO analytics_export_jobs (
                        job_id, dataset_type, portfolio_id, status, request_fingerprint,
                        request_payload, result_format, compression
                    ) VALUES (
                        'aexp_orphaned', 'positions', 'PORT-MISSING', 'accepted',
                        'orphaned-fingerprint', '{}'::json, 'json', 'none'
                    )
                    """
                )
            )

            rejected_cutover = connection.begin_nested()
            with pytest.raises(DBAPIError, match="analytics export tenant cutover found 1"):
                migration["upgrade"]()
            rejected_cutover.rollback()

            columns = {
                column["name"]
                for column in inspect(connection).get_columns("analytics_export_jobs")
            }
            assert "tenant_id" not in columns
            connection.execute(
                text("DELETE FROM analytics_export_jobs WHERE job_id = 'aexp_orphaned'")
            )

            migration["upgrade"]()

            assert (
                connection.execute(
                    text(
                        "SELECT tenant_id FROM analytics_export_jobs WHERE job_id = 'aexp_legacy_b'"
                    )
                ).scalar_one()
                == "tenant-b"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT job_id FROM analytics_export_jobs "
                        "WHERE tenant_id = 'tenant-a' AND job_id = 'aexp_legacy_b'"
                    )
                ).scalar_one_or_none()
                is None
            )
            assert (
                connection.execute(
                    text(
                        "SELECT job_id FROM analytics_export_jobs "
                        "WHERE tenant_id = 'tenant-a' "
                        "AND dataset_type = 'positions' "
                        "AND request_fingerprint = 'shared-fingerprint'"
                    )
                ).scalar_one_or_none()
                is None
            )
            foreign_update = connection.execute(
                text(
                    "UPDATE analytics_export_jobs SET status = 'failed' "
                    "WHERE tenant_id = 'tenant-a' AND job_id = 'aexp_legacy_b'"
                )
            )
            assert foreign_update.rowcount == 0
            assert (
                connection.execute(
                    text(
                        "SELECT status FROM analytics_export_jobs "
                        "WHERE tenant_id = 'tenant-b' AND job_id = 'aexp_legacy_b'"
                    )
                ).scalar_one()
                == "completed"
            )

            invalid_insert = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO analytics_export_jobs (
                            job_id, tenant_id, dataset_type, portfolio_id, status,
                            request_fingerprint, request_payload, result_format, compression
                        ) VALUES (
                            'aexp_forged_a', 'tenant-a', 'positions', 'PORT-EXPORT-B', 'accepted',
                            'forged-fingerprint', '{}'::json, 'json', 'none'
                        )
                        """
                    )
                )
            invalid_insert.rollback()

            migration["downgrade"]()
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("analytics_export_jobs")
            }
            assert "tenant_id" not in columns
        finally:
            transaction.rollback()
