"""PostgreSQL proof for the fail-closed portfolio tenant cutover."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import String, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c165b2c3d52c_fix_require_portfolio_tenant.py"
)
SIMULATION_SUCCESSOR = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c166b2c3d52d_fix_bind_simulation_session_tenant.py"
)
ANALYTICS_EXPORT_SUCCESSOR = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c167b2c3d52e_fix_bind_analytics_export_job_tenant.py"
)

PORTFOLIO_INSERT = text(
    """
    INSERT INTO portfolios (
        portfolio_id,
        tenant_id,
        legal_book_id,
        base_currency,
        open_date,
        risk_exposure,
        investment_time_horizon,
        portfolio_type,
        booking_center_code,
        client_id,
        is_leverage_allowed,
        status
    ) VALUES (
        :portfolio_id,
        :tenant_id,
        :legal_book_id,
        'USD',
        DATE '2026-01-01',
        'balanced',
        'long_term',
        'discretionary',
        'SG_BOOKING',
        'CLIENT-001',
        FALSE,
        'active'
    )
    """
)

LEGACY_INGESTION_JOB_INSERT = text(
    """
    INSERT INTO ingestion_jobs (
        job_id,
        endpoint,
        entity_type,
        accepted_count,
        correlation_id,
        request_id,
        trace_id,
        request_payload_policy_version,
        request_payload_classification,
        request_payload_representation,
        request_payload_replay_eligible,
        request_payload_partial_replay_eligible,
        request_payload_retention_authority
    ) VALUES (
        'TENANT-CUTOVER-JOB',
        '/ingest/transactions',
        'transaction',
        1,
        'tenant-cutover-correlation',
        'tenant-cutover-request',
        'tenant-cutover-trace',
        'ingestion-evidence-policy.v1',
        'internal',
        'fingerprint_only',
        FALSE,
        FALSE,
        'lotus-core#798'
    )
    """
)

VERIFIED_TENANT_AUDIT_INSERT = text(
    """
    INSERT INTO enterprise_security_audit_events (
        event_id,
        occurred_at,
        component,
        route_template,
        method,
        decision,
        reason,
        service_identity,
        actor_id,
        tenant_id,
        role,
        identity_posture,
        correlation_id,
        trace_id,
        policy_version
    ) VALUES (
        '79800000-0000-0000-0000-000000000001',
        now() - INTERVAL '1 second',
        'ingestion_service',
        '/ingest/transactions',
        'POST',
        'ALLOW',
        'authorized',
        'lotus-integration-test',
        'tenant-cutover-actor',
        'tenant-test',
        'operator',
        'verified',
        'tenant-cutover-correlation',
        'tenant-cutover-trace',
        'enterprise-security.v1'
    )
    """
)

UNRELATED_REUSED_CORRELATION_AUDIT_INSERT = text(
    """
    INSERT INTO enterprise_security_audit_events (
        event_id,
        occurred_at,
        component,
        route_template,
        method,
        decision,
        reason,
        service_identity,
        actor_id,
        tenant_id,
        role,
        identity_posture,
        correlation_id,
        trace_id,
        policy_version
    ) VALUES (
        '79800000-0000-0000-0000-000000000002',
        now() - INTERVAL '1 second',
        'query_service',
        '/ingest/transactions',
        'POST',
        'ALLOW',
        'authorized',
        'lotus-unrelated-service',
        'unrelated-actor',
        'tenant-wrong',
        'operator',
        'verified',
        'tenant-cutover-correlation',
        'tenant-cutover-trace',
        'enterprise-security.v1'
    )
    """
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _reset_development_cutover(
    migration: dict[str, Any],
    simulation_successor: dict[str, Any],
    analytics_export_successor: dict[str, Any],
    connection,
) -> None:
    analytics_export_columns = {
        column["name"] for column in inspect(connection).get_columns("analytics_export_jobs")
    }
    if "tenant_id" in analytics_export_columns:
        analytics_export_successor["downgrade"]()

    simulation_columns = {
        column["name"] for column in inspect(connection).get_columns("simulation_sessions")
    }
    if "tenant_id" in simulation_columns:
        simulation_successor["downgrade"]()

    indexes = {index["name"] for index in inspect(connection).get_indexes("portfolios")}
    if "ix_portfolios_tenant_portfolio_id" not in indexes:
        return
    ingestion_indexes = {
        index["name"] for index in inspect(connection).get_indexes("ingestion_jobs")
    }
    if "ix_ingestion_jobs_tenant_endpoint_idempotency_submitted" in ingestion_indexes:
        migration["downgrade"]()
        return

    operations = Operations(MigrationContext.configure(connection))
    if "ix_ingestion_jobs_tenant_submitted_at" in ingestion_indexes:
        operations.drop_index(
            "ix_ingestion_jobs_tenant_submitted_at",
            table_name="ingestion_jobs",
        )
        operations.drop_constraint(
            "ck_ingestion_jobs_tenant_authority",
            "ingestion_jobs",
            type_="check",
        )
        operations.drop_column("ingestion_jobs", "tenant_id")
    operations.drop_index("ix_portfolios_tenant_portfolio_id", table_name="portfolios")
    operations.drop_constraint(
        "ck_portfolios_valuation_book_scope_complete",
        "portfolios",
        type_="check",
    )
    operations.alter_column(
        "portfolios",
        "tenant_id",
        existing_type=String(length=128),
        type_=String(),
        nullable=True,
    )
    operations.create_check_constraint(
        "ck_portfolios_valuation_book_scope_complete",
        "portfolios",
        "(tenant_id IS NULL AND legal_book_id IS NULL) OR "
        "(tenant_id IS NOT NULL AND legal_book_id IS NOT NULL "
        "AND tenant_id = btrim(tenant_id) AND legal_book_id = btrim(legal_book_id) "
        "AND tenant_id <> '' AND legal_book_id <> '')",
    )


def test_portfolio_tenant_cutover_rejects_ambiguous_rows_then_applies_and_rolls_back(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    simulation_successor: dict[str, Any] = runpy.run_path(str(SIMULATION_SUCCESSOR))
    analytics_export_successor: dict[str, Any] = runpy.run_path(str(ANALYTICS_EXPORT_SUCCESSOR))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        _bind_operations(simulation_successor, connection)
        _bind_operations(analytics_export_successor, connection)
        _reset_development_cutover(
            migration,
            simulation_successor,
            analytics_export_successor,
            connection,
        )
        connection.execute(
            PORTFOLIO_INSERT,
            {
                "portfolio_id": "TENANT-CUTOVER-AMBIGUOUS",
                "tenant_id": None,
                "legal_book_id": None,
            },
        )
        connection.execute(LEGACY_INGESTION_JOB_INSERT)
        connection.execute(UNRELATED_REUSED_CORRELATION_AUDIT_INSERT)

        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError) as exc_info:
            migration["upgrade"]()
        savepoint.rollback()
        error_text = str(exc_info.value)
        assert "portfolio tenant cutover found 1 ambiguous root row" in error_text
        assert "TENANT-CUTOVER-AMBIGUOUS" in error_text

        connection.execute(
            text(
                """
                UPDATE portfolios
                SET tenant_id = 'tenant-test', legal_book_id = 'book-test'
                WHERE portfolio_id = 'TENANT-CUTOVER-AMBIGUOUS'
                """
            )
        )

        ingestion_savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError) as ingestion_error:
            migration["upgrade"]()
        ingestion_savepoint.rollback()
        assert "ingestion job tenant cutover found 1 unattributable row" in str(
            ingestion_error.value
        )
        assert "TENANT-CUTOVER-JOB" in str(ingestion_error.value)
        assert "tenant_id" not in {
            column["name"] for column in inspect(connection).get_columns("ingestion_jobs")
        }

        connection.execute(VERIFIED_TENANT_AUDIT_INSERT)
        migration["upgrade"]()

        columns = {
            column["name"]: column for column in inspect(connection).get_columns("portfolios")
        }
        assert columns["tenant_id"]["nullable"] is False
        assert str(columns["tenant_id"]["type"]) == "VARCHAR(128)"
        assert any(
            index["name"] == "ix_portfolios_tenant_portfolio_id"
            and index["column_names"] == ["tenant_id", "portfolio_id"]
            for index in inspect(connection).get_indexes("portfolios")
        )
        ingestion_columns = {
            column["name"]: column for column in inspect(connection).get_columns("ingestion_jobs")
        }
        assert ingestion_columns["tenant_id"]["nullable"] is False
        assert str(ingestion_columns["tenant_id"]["type"]) == "VARCHAR(128)"
        assert any(
            index["name"] == "ix_ingestion_jobs_tenant_submitted_at"
            for index in inspect(connection).get_indexes("ingestion_jobs")
        )
        assert any(
            index["name"] == "ix_ingestion_jobs_tenant_endpoint_idempotency_submitted"
            and index["column_names"][:3] == ["tenant_id", "endpoint", "idempotency_key"]
            for index in inspect(connection).get_indexes("ingestion_jobs")
        )
        assert (
            connection.scalar(
                text("SELECT tenant_id FROM ingestion_jobs WHERE job_id = 'TENANT-CUTOVER-JOB'")
            )
            == "tenant-test"
        )

        connection.execute(
            PORTFOLIO_INSERT,
            {
                "portfolio_id": "TENANT-CUTOVER-NO-BOOK",
                "tenant_id": "tenant-test",
                "legal_book_id": None,
            },
        )
        downgrade_savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError) as downgrade_error:
            migration["downgrade"]()
        downgrade_savepoint.rollback()
        assert "portfolio tenant downgrade found 1 row(s) without legal-book scope" in str(
            downgrade_error.value
        )
        assert "TENANT-CUTOVER-NO-BOOK" in str(downgrade_error.value)
        assert "tenant_id" in {
            column["name"] for column in inspect(connection).get_columns("ingestion_jobs")
        }
        invalid_savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                PORTFOLIO_INSERT,
                {
                    "portfolio_id": "TENANT-CUTOVER-NULL",
                    "tenant_id": None,
                    "legal_book_id": None,
                },
            )
        invalid_savepoint.rollback()

        connection.execute(
            text(
                """
                UPDATE portfolios
                SET legal_book_id = 'book-test'
                WHERE portfolio_id = 'TENANT-CUTOVER-NO-BOOK'
                """
            )
        )
        migration["downgrade"]()
        downgraded_columns = {
            column["name"]: column for column in inspect(connection).get_columns("portfolios")
        }
        assert downgraded_columns["tenant_id"]["nullable"] is True
        assert "tenant_id" not in {
            column["name"] for column in inspect(connection).get_columns("ingestion_jobs")
        }
