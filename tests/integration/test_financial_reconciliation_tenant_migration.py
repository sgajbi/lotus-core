"""PostgreSQL proof for financial-reconciliation tenant authority cutover."""

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
    / "c174b2c3d535_scope_financial_reconciliation_tenant.py"
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

LEGACY_RUN_INSERT = text(
    """
    INSERT INTO financial_reconciliation_runs (
        run_id, reconciliation_type, portfolio_id, business_date, epoch,
        aggregation_revision, status, requested_by, dedupe_key
    ) VALUES (
        :run_id, 'transaction_cashflow', :portfolio_id, DATE '2026-09-01', 3,
        7, 'COMPLETED', 'migration-test', :dedupe_key
    )
    """
)

LEGACY_FINDING_INSERT = text(
    """
    INSERT INTO financial_reconciliation_findings (
        finding_id, run_id, reconciliation_type, finding_type, severity,
        portfolio_id, business_date, epoch, owner, repair_recommendation
    ) VALUES (
        :finding_id, :run_id, 'transaction_cashflow', 'missing_cashflow', 'ERROR',
        :portfolio_id, DATE '2026-09-01', 3, 'TRANSACTION_OPERATIONS',
        'REGENERATE_CASHFLOW'
    )
    """
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def test_reconciliation_tenant_cutover_backfills_fences_dedupes_and_rolls_back(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        if "authority_scope" in {
            column["name"]
            for column in inspect(connection).get_columns("financial_reconciliation_runs")
        }:
            migration["downgrade"]()

    with db_engine.connect() as legacy_writer, db_engine.connect() as cutover_connection:
        legacy_transaction = legacy_writer.begin()
        legacy_writer.execute(
            text("LOCK TABLE financial_reconciliation_runs IN ROW EXCLUSIVE MODE")
        )
        cutover_transaction = cutover_connection.begin()
        _bind_operations(migration, cutover_connection)
        with pytest.raises(DBAPIError, match="lock timeout"):
            migration["upgrade"]()
        cutover_transaction.rollback()
        legacy_transaction.rollback()

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        for tenant_id, portfolio_id in (
            ("tenant-a", "PORT-RECON-A"),
            ("tenant-b", "PORT-RECON-B"),
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
            LEGACY_RUN_INSERT,
            {
                "run_id": "run-orphan",
                "portfolio_id": "PORT-MISSING",
                "dedupe_key": "dedupe-orphan",
            },
        )
        failed_cutover = connection.begin_nested()
        with pytest.raises(DBAPIError, match="unattributable run"):
            migration["upgrade"]()
        failed_cutover.rollback()
        connection.execute(
            text("DELETE FROM financial_reconciliation_runs WHERE run_id = 'run-orphan'")
        )

        connection.execute(
            text(
                """
                INSERT INTO processed_events (
                    event_id, portfolio_id, service_name, correlation_id
                ) VALUES (
                    'event-orphan', 'PORT-MISSING',
                    'financial-reconciliation-requested', 'corr-event-orphan'
                )
                """
            )
        )
        failed_event_cutover = connection.begin_nested()
        with pytest.raises(DBAPIError, match="event-fence tenant cutover"):
            migration["upgrade"]()
        failed_event_cutover.rollback()
        connection.execute(text("DELETE FROM processed_events WHERE event_id = 'event-orphan'"))

        connection.execute(
            text(
                """
                INSERT INTO processed_events (
                    event_id, portfolio_id, service_name, tenant_id, correlation_id
                ) VALUES (
                    'event-conflicting-tenant', 'PORT-RECON-A',
                    'financial-reconciliation-requested', 'tenant-b',
                    'corr-event-conflicting-tenant'
                )
                """
            )
        )
        conflicting_event_cutover = connection.begin_nested()
        with pytest.raises(DBAPIError, match="event-fence tenant cutover"):
            migration["upgrade"]()
        conflicting_event_cutover.rollback()
        connection.execute(
            text("DELETE FROM processed_events WHERE event_id = 'event-conflicting-tenant'")
        )

        connection.execute(
            text(
                """
                INSERT INTO processed_events (
                    event_id, portfolio_id, service_name, correlation_id
                ) VALUES (
                    'event-owner', 'PORT-RECON-A',
                    'financial-reconciliation-requested', 'corr-event-owner'
                )
                """
            )
        )

        connection.execute(
            LEGACY_RUN_INSERT,
            {
                "run_id": "run-a",
                "portfolio_id": "PORT-RECON-A",
                "dedupe_key": "dedupe-shared",
            },
        )
        connection.execute(
            LEGACY_FINDING_INSERT,
            {
                "finding_id": "finding-a",
                "run_id": "run-a",
                "portfolio_id": "PORT-RECON-A",
            },
        )
        connection.execute(
            LEGACY_RUN_INSERT,
            {
                "run_id": "run-estate",
                "portfolio_id": None,
                "dedupe_key": "dedupe-estate",
            },
        )
        connection.execute(
            LEGACY_FINDING_INSERT,
            {
                "finding_id": "finding-estate",
                "run_id": "run-estate",
                "portfolio_id": "PORT-RECON-A",
            },
        )

        migration["upgrade"]()

        assert connection.execute(
            text(
                "SELECT authority_scope, tenant_id FROM financial_reconciliation_runs "
                "WHERE run_id = 'run-a'"
            )
        ).one() == ("TENANT", "tenant-a")
        assert connection.execute(
            text(
                "SELECT authority_scope, tenant_id FROM financial_reconciliation_runs "
                "WHERE run_id = 'run-estate'"
            )
        ).one() == ("ESTATE", None)
        assert (
            connection.scalar(
                text("SELECT tenant_id FROM processed_events WHERE event_id = 'event-owner'")
            )
            == "tenant-a"
        )

        missing_event_tenant = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO processed_events (
                        event_id, portfolio_id, service_name, correlation_id
                    ) VALUES (
                        'event-missing-tenant', 'PORT-RECON-A',
                        'financial-reconciliation-requested', 'corr-event-missing'
                    )
                    """
                )
            )
        missing_event_tenant.rollback()

        legacy_run_writer = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                LEGACY_RUN_INSERT,
                {
                    "run_id": "run-late-legacy-writer",
                    "portfolio_id": "PORT-RECON-A",
                    "dedupe_key": "dedupe-late-legacy-writer",
                },
            )
        legacy_run_writer.rollback()
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM financial_reconciliation_runs "
                    "WHERE run_id = 'run-late-legacy-writer'"
                )
            )
            == 0
        )

        legacy_finding_writer = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                LEGACY_FINDING_INSERT,
                {
                    "finding_id": "finding-late-legacy-writer",
                    "run_id": "run-a",
                    "portfolio_id": "PORT-RECON-A",
                },
            )
        legacy_finding_writer.rollback()
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM financial_reconciliation_findings "
                    "WHERE finding_id = 'finding-late-legacy-writer'"
                )
            )
            == 0
        )

        connection.execute(
            text(
                """
                INSERT INTO processed_events (
                    event_id, portfolio_id, service_name, tenant_id, correlation_id
                ) VALUES (
                    'event-owner', 'PORT-RECON-B',
                    'financial-reconciliation-requested', 'tenant-b', 'corr-event-other'
                )
                """
            )
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM processed_events "
                    "WHERE event_id = 'event-owner' "
                    "AND service_name = 'financial-reconciliation-requested'"
                )
            )
            == 2
        )
        duplicate_owner_event = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO processed_events (
                        event_id, portfolio_id, service_name, tenant_id, correlation_id
                    ) VALUES (
                        'event-owner', 'PORT-RECON-A',
                        'financial-reconciliation-requested', 'tenant-a',
                        'corr-event-owner-duplicate'
                    )
                    """
                )
            )
        duplicate_owner_event.rollback()
        assert connection.execute(
            text(
                "SELECT authority_scope, tenant_id FROM financial_reconciliation_findings "
                "WHERE finding_id = 'finding-a'"
            )
        ).one() == ("TENANT", "tenant-a")
        assert connection.execute(
            text(
                "SELECT authority_scope, tenant_id FROM financial_reconciliation_findings "
                "WHERE finding_id = 'finding-estate'"
            )
        ).one() == ("ESTATE", None)

        mismatched_run = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO financial_reconciliation_runs (
                        run_id, authority_scope, tenant_id, reconciliation_type,
                        portfolio_id, status, dedupe_key
                    ) VALUES (
                        'run-mismatch', 'TENANT', 'tenant-b', 'transaction_cashflow',
                        'PORT-RECON-A', 'COMPLETED', 'dedupe-mismatch'
                    )
                    """
                )
            )
        mismatched_run.rollback()

        mismatched_finding = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO financial_reconciliation_findings (
                        finding_id, authority_scope, tenant_id, run_id,
                        reconciliation_type, finding_type, severity, portfolio_id,
                        owner, repair_recommendation
                    ) VALUES (
                        'finding-mismatch', 'TENANT', 'tenant-b', 'run-a',
                        'transaction_cashflow', 'missing_cashflow', 'ERROR',
                        'PORT-RECON-B', 'TRANSACTION_OPERATIONS', 'REGENERATE_CASHFLOW'
                    )
                    """
                )
            )
        mismatched_finding.rollback()

        mismatched_estate_finding = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO financial_reconciliation_findings (
                        finding_id, authority_scope, tenant_id, run_id,
                        reconciliation_type, finding_type, severity, portfolio_id,
                        owner, repair_recommendation
                    ) VALUES (
                        'finding-estate-to-tenant-run', 'ESTATE', NULL, 'run-a',
                        'transaction_cashflow', 'missing_cashflow', 'ERROR', NULL,
                        'TRANSACTION_OPERATIONS', 'REGENERATE_CASHFLOW'
                    )
                    """
                )
            )
        mismatched_estate_finding.rollback()

        duplicate_tenant_dedupe = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO financial_reconciliation_runs (
                        run_id, authority_scope, tenant_id, reconciliation_type,
                        portfolio_id, status, dedupe_key
                    ) VALUES (
                        'run-a-duplicate-dedupe', 'TENANT', 'tenant-a',
                        'transaction_cashflow', 'PORT-RECON-A', 'COMPLETED',
                        'dedupe-shared'
                    )
                    """
                )
            )
        duplicate_tenant_dedupe.rollback()

        connection.execute(
            text(
                """
                INSERT INTO financial_reconciliation_runs (
                    run_id, authority_scope, tenant_id, reconciliation_type,
                    portfolio_id, status, dedupe_key
                ) VALUES (
                    'run-b', 'TENANT', 'tenant-b', 'transaction_cashflow',
                    'PORT-RECON-B', 'COMPLETED', 'dedupe-shared'
                )
                """
            )
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM financial_reconciliation_runs "
                    "WHERE dedupe_key = 'dedupe-shared'"
                )
            )
            == 2
        )

        refused_downgrade = connection.begin_nested()
        with pytest.raises(DBAPIError, match="global dedupe collision"):
            migration["downgrade"]()
        refused_downgrade.rollback()

        connection.execute(text("DELETE FROM financial_reconciliation_runs WHERE run_id = 'run-b'"))
        connection.execute(
            text(
                """
                INSERT INTO financial_reconciliation_runs (
                    run_id, authority_scope, tenant_id, reconciliation_type,
                    portfolio_id, status, dedupe_key
                ) VALUES (
                    'run-tenant-wide', 'TENANT', 'tenant-a',
                    'transaction_cashflow', NULL, 'COMPLETED', 'dedupe-tenant-wide'
                )
                """
            )
        )
        tenant_wide_refused_downgrade = connection.begin_nested()
        with pytest.raises(DBAPIError, match="tenant-wide run"):
            migration["downgrade"]()
        tenant_wide_refused_downgrade.rollback()
        connection.execute(
            text("DELETE FROM financial_reconciliation_runs WHERE run_id = 'run-tenant-wide'")
        )
        migration["downgrade"]()
        run_columns = {
            column["name"]
            for column in inspect(connection).get_columns("financial_reconciliation_runs")
        }
        assert "authority_scope" not in run_columns
        assert "tenant_id" not in run_columns

        migration["upgrade"]()
        assert "authority_scope" in {
            column["name"]
            for column in inspect(connection).get_columns("financial_reconciliation_runs")
        }
        assert connection.execute(
            text(
                "SELECT authority_scope, tenant_id FROM financial_reconciliation_runs "
                "WHERE run_id = 'run-a'"
            )
        ).one() == ("TENANT", "tenant-a")
        assert connection.execute(
            text(
                "SELECT authority_scope, tenant_id FROM financial_reconciliation_runs "
                "WHERE run_id = 'run-estate'"
            )
        ).one() == ("ESTATE", None)
