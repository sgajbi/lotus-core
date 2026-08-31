"""PostgreSQL apply/rollback proof for durable ingestion replay outcomes."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import TextClause

from tests.integration.ingestion_job_sql_fixture import (
    transaction_ingestion_job_insert_fragments,
)
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c121b2c3d4fa_feat_add_ingestion_failure_outcomes.py"
)


def _job_insert(connection: Connection) -> TextClause:
    evidence_columns, evidence_values = transaction_ingestion_job_insert_fragments(connection)
    return text(
        f"""
    INSERT INTO ingestion_jobs (
        job_id,
        endpoint,
        entity_type,
        status,
        accepted_count,
        correlation_id,
        request_id,
        trace_id,
        failure_reason,
        failure_status_code,
        failure_code,
        failure_detail,
        failure_headers{evidence_columns}
    ) VALUES (
        :job_id,
        '/ingest/transactions',
        'transaction',
        :status,
        1,
        'corr-ingestion-outcome',
        'req-ingestion-outcome',
        'trace-ingestion-outcome',
        :failure_reason,
        :failure_status_code,
        :failure_code,
        CAST(:failure_detail AS JSON),
        CAST(:failure_headers AS JSON){evidence_values}
    )
    """
    )


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _normalize_to_previous_revision(
    migration: dict[str, Any],
    connection,
) -> None:
    """Remove only pre-created c121 state from either fixture revision."""

    inspector = inspect(connection)
    check_names = {
        constraint["name"] for constraint in inspector.get_check_constraints("ingestion_jobs")
    }
    column_names = {column["name"] for column in inspector.get_columns("ingestion_jobs")}
    operations = migration["upgrade"].__globals__["op"]
    if "ck_ingestion_jobs_failure_outcome_complete" in check_names:
        operations.drop_constraint(
            "ck_ingestion_jobs_failure_outcome_complete",
            "ingestion_jobs",
            type_="check",
        )
    for column_name in (
        "failure_headers",
        "failure_detail",
        "failure_code",
        "failure_status_code",
    ):
        if column_name in column_names:
            operations.drop_column("ingestion_jobs", column_name)


def test_ingestion_failure_outcome_migration_round_trip_and_constraint(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        head_schema = connection.begin_nested()
        _bind_operations(migration, connection)
        _normalize_to_previous_revision(migration, connection)
        columns = {column["name"] for column in inspect(connection).get_columns("ingestion_jobs")}
        assert {
            "failure_status_code",
            "failure_code",
            "failure_detail",
            "failure_headers",
        }.isdisjoint(columns)

        migration["upgrade"]()
        columns = {column["name"] for column in inspect(connection).get_columns("ingestion_jobs")}
        assert {
            "failure_status_code",
            "failure_code",
            "failure_detail",
            "failure_headers",
        } <= columns
        validated = connection.execute(
            text(
                """
                SELECT convalidated
                FROM pg_constraint
                WHERE conname = 'ck_ingestion_jobs_failure_outcome_complete'
                """
            )
        ).scalar_one()
        assert validated is True
        job_insert = _job_insert(connection)

        base = {
            "tenant_id": TEST_TENANT_ID,
            "status": "queued",
            "failure_reason": None,
            "failure_status_code": None,
            "failure_code": None,
            "failure_detail": None,
            "failure_headers": None,
        }
        connection.execute(job_insert, base | {"job_id": "job-outcome-legacy"})
        connection.execute(
            job_insert,
            base
            | {
                "job_id": "job-outcome-complete",
                "status": "failed",
                "failure_reason": "broker unavailable",
                "failure_status_code": 503,
                "failure_code": "INGESTION_PUBLISH_FAILED",
                "failure_detail": '{"retryable": true}',
                "failure_headers": '{"Retry-After": "30"}',
            },
        )

        invalid_outcomes = [
            {"failure_status_code": 503},
            {"failure_code": "INGESTION_PUBLISH_FAILED"},
            {"failure_detail": '{"retryable": true}'},
            {"failure_headers": '{"Retry-After": "30"}'},
            {"failure_status_code": 399, "failure_code": "INVALID_STATUS"},
            {"failure_status_code": 600, "failure_code": "INVALID_STATUS"},
            {"failure_status_code": 500, "failure_code": ""},
            {"failure_status_code": 500, "failure_code": " NOT_NORMALIZED "},
        ]
        for sequence, outcome in enumerate(invalid_outcomes, start=1):
            savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    job_insert,
                    base
                    | {
                        "job_id": f"job-outcome-invalid-{sequence}",
                        "status": "failed",
                    }
                    | outcome,
                )
            savepoint.rollback()

        migration["downgrade"]()
        downgraded_columns = {
            column["name"] for column in inspect(connection).get_columns("ingestion_jobs")
        }
        assert {
            "failure_status_code",
            "failure_code",
            "failure_detail",
            "failure_headers",
        }.isdisjoint(downgraded_columns)

        migration["upgrade"]()
        final_columns = {
            column["name"] for column in inspect(connection).get_columns("ingestion_jobs")
        }
        assert {
            "failure_status_code",
            "failure_code",
            "failure_detail",
            "failure_headers",
        } <= final_columns
        head_schema.rollback()
