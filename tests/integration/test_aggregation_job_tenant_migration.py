"""PostgreSQL proof for source-owned portfolio aggregation job tenants."""

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
    / "c168b2c3d52f_feat_add_aggregation_job_tenant.py"
)

PORTFOLIO_INSERT = text(
    """
    INSERT INTO portfolios (
        portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
        risk_exposure, investment_time_horizon, portfolio_type,
        booking_center_code, client_id, is_leverage_allowed, status
    ) VALUES (
        :portfolio_id, :tenant_id, :legal_book_id, 'USD', DATE '2026-01-01',
        'balanced', 'long_term', 'discretionary', 'SG_BOOKING',
        :client_id, FALSE, 'active'
    )
    """
)

LEGACY_JOB_INSERT = text(
    """
    INSERT INTO portfolio_aggregation_jobs (
        portfolio_id, aggregation_date, status, attempt_count,
        target_epoch, source_revision
    ) VALUES (
        :portfolio_id, :aggregation_date, 'PENDING', 0, 3, 1
    )
    """
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def test_aggregation_job_cutover_quiesces_backfills_and_rejects_false_authority(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        if "tenant_id" in {
            column["name"]
            for column in inspect(connection).get_columns("portfolio_aggregation_jobs")
        }:
            migration["downgrade"]()

    with (
        db_engine.connect() as legacy_writer,
        db_engine.connect() as cutover_connection,
    ):
        legacy_transaction = legacy_writer.begin()
        legacy_writer.execute(text("LOCK TABLE portfolio_aggregation_jobs IN ROW EXCLUSIVE MODE"))
        cutover_transaction = cutover_connection.begin()
        _bind_operations(migration, cutover_connection)
        with pytest.raises(DBAPIError, match="lock timeout"):
            migration["upgrade"]()
        cutover_transaction.rollback()
        legacy_transaction.rollback()

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        for tenant_id, portfolio_id in (
            ("tenant-a", "PORT-AGG-A"),
            ("tenant-b", "PORT-AGG-B"),
        ):
            connection.execute(
                PORTFOLIO_INSERT,
                {
                    "portfolio_id": portfolio_id,
                    "tenant_id": tenant_id,
                    "legal_book_id": f"BOOK-{tenant_id}",
                    "client_id": f"CLIENT-{tenant_id}",
                },
            )

        connection.execute(
            LEGACY_JOB_INSERT,
            {"portfolio_id": "PORT-MISSING", "aggregation_date": "2026-09-01"},
        )
        failed_cutover = connection.begin_nested()
        with pytest.raises(DBAPIError, match="unattributable"):
            migration["upgrade"]()
        failed_cutover.rollback()
        connection.execute(
            text("DELETE FROM portfolio_aggregation_jobs WHERE portfolio_id = 'PORT-MISSING'")
        )

        connection.execute(
            LEGACY_JOB_INSERT,
            {"portfolio_id": "PORT-AGG-A", "aggregation_date": "2026-09-01"},
        )
        migration["upgrade"]()

        assert (
            connection.scalar(
                text(
                    "SELECT tenant_id FROM portfolio_aggregation_jobs "
                    "WHERE portfolio_id = 'PORT-AGG-A'"
                )
            )
            == "tenant-a"
        )

        mismatched_tenant = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO portfolio_aggregation_jobs (
                        tenant_id, portfolio_id, aggregation_date, status,
                        attempt_count, target_epoch, source_revision
                    ) VALUES (
                        'tenant-b', 'PORT-AGG-A', DATE '2026-09-02', 'PENDING', 0, 3, 1
                    )
                    """
                )
            )
        mismatched_tenant.rollback()

        blank_tenant = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO portfolio_aggregation_jobs (
                        tenant_id, portfolio_id, aggregation_date, status,
                        attempt_count, target_epoch, source_revision
                    ) VALUES (
                        '', 'PORT-AGG-A', DATE '2026-09-02', 'PENDING', 0, 3, 1
                    )
                    """
                )
            )
        blank_tenant.rollback()

        connection.execute(
            text(
                """
                INSERT INTO portfolio_aggregation_jobs (
                    tenant_id, portfolio_id, aggregation_date, status,
                    attempt_count, target_epoch, source_revision
                ) VALUES (
                    'tenant-b', 'PORT-AGG-B', DATE '2026-09-01', 'PENDING', 0, 3, 1
                )
                """
            )
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM portfolio_aggregation_jobs "
                    "WHERE aggregation_date = DATE '2026-09-01'"
                )
            )
            == 2
        )

        constraint_names = {
            constraint["name"]
            for constraint in inspect(connection).get_unique_constraints(
                "portfolio_aggregation_jobs"
            )
        }
        assert "uq_portfolio_aggregation_jobs_tenant_portfolio_date" in constraint_names
