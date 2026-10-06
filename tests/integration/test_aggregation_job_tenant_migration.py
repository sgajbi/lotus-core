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

from tests.test_support.selected_history_migration_dependencies import (
    restore_selected_history_portfolio_foreign_keys,
    suspend_selected_history_portfolio_foreign_keys,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c168b2c3d52f_feat_add_aggregation_job_tenant.py"
)
SOURCE_REVISION_MIGRATION = MIGRATION.with_name(
    "c177b2c3d538_add_transaction_source_evidence_revisions.py"
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


def _source_revision_semantics(connection) -> tuple[list[dict[str, Any]], tuple, tuple]:
    foreign_keys = inspect(connection).get_foreign_keys(
        "transaction_source_revisions", schema="public"
    )
    assert {
        "fk_source_revision_portfolio_owner",
        "fk_source_revision_operation_owner",
        "fk_source_revision_transaction_owner",
    } <= {foreign_key["name"] for foreign_key in foreign_keys}
    constraints = tuple(
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid), convalidated FROM pg_constraint "
                "WHERE conrelid = 'public.transaction_source_revisions'::regclass "
                "AND contype = 'f' ORDER BY conname"
            )
        )
    )
    assert all(row[2] for row in constraints)
    trigger = tuple(
        connection.execute(
            text(
                """
                SELECT t.tgname, pn.nspname, p.proname,
                       pg_get_function_identity_arguments(p.oid), t.tgtype, t.tgenabled,
                       t.tgconstraint, pg_get_triggerdef(t.oid), pg_get_functiondef(p.oid)
                FROM pg_trigger t
                JOIN pg_proc p ON p.oid = t.tgfoid
                JOIN pg_namespace pn ON pn.oid = p.pronamespace
                WHERE t.tgrelid = 'public.transaction_source_revisions'::regclass
                  AND NOT t.tgisinternal
                """
            )
        ).one()
    )
    assert trigger[:7] == (
        "transaction_source_revision_immutable",
        "public",
        "reject_transaction_source_revision_mutation",
        "",
        27,  # BEFORE UPDATE OR DELETE, FOR EACH ROW.
        "O",
        0,
    )
    return foreign_keys, constraints, trigger


def test_historical_rollback_setup_refuses_missing_newer_tenant_foreign_key(
    db_engine,
    clean_db,
) -> None:
    with db_engine.begin() as connection:
        missing_key = connection.begin_nested()
        connection.execute(
            text(
                "ALTER TABLE portfolio_selected_history_observations "
                "DROP CONSTRAINT fk_portfolio_selected_history_observations_tenant_portfolio"
            )
        )
        with pytest.raises(AssertionError):
            suspend_selected_history_portfolio_foreign_keys(connection)
        missing_key.rollback()
        assert "fk_portfolio_selected_history_observations_tenant_portfolio" in {
            foreign_key["name"]
            for foreign_key in inspect(connection).get_foreign_keys(
                "portfolio_selected_history_observations"
            )
        }


def test_aggregation_job_cutover_quiesces_backfills_and_rejects_false_authority(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    source_migration: dict[str, Any] = runpy.run_path(str(SOURCE_REVISION_MIGRATION))

    with db_engine.begin() as connection:
        original_source_semantics = _source_revision_semantics(connection)
        suspend_selected_history_portfolio_foreign_keys(connection)
        _bind_operations(source_migration, connection)
        # Real empty-history refusal, never a shortcut removal of owner constraints.
        source_migration["downgrade"]()
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
        restore_selected_history_portfolio_foreign_keys(connection)
        _bind_operations(source_migration, connection)
        source_migration["upgrade"]()
        assert _source_revision_semantics(connection) == original_source_semantics

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
