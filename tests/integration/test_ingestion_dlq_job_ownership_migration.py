"""PostgreSQL proof for durable ingestion DLQ ownership and legacy isolation."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.integration.ingestion_job_sql_fixture import (
    transaction_ingestion_job_insert_fragments,
)
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c133b2c3d506_feat_add_ingestion_dlq_job_ownership.py"
)


def _bind_operations(migration: dict[str, Any], connection) -> Operations:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations
    return operations


def _normalize_to_previous_revision(operations: Operations, connection) -> None:
    inspector = inspect(connection)
    dlq_indexes = {row["name"] for row in inspector.get_indexes("consumer_dlq_events")}
    replay_indexes = {row["name"] for row in inspector.get_indexes("consumer_dlq_replay_audit")}
    dlq_foreign_keys = {row["name"] for row in inspector.get_foreign_keys("consumer_dlq_events")}
    if "ix_consumer_dlq_replay_audit_job_requested_id" in replay_indexes:
        operations.drop_index(
            "ix_consumer_dlq_replay_audit_job_requested_id",
            table_name="consumer_dlq_replay_audit",
        )
    if "ix_consumer_dlq_events_job_observed_id" in dlq_indexes:
        operations.drop_index(
            "ix_consumer_dlq_events_job_observed_id",
            table_name="consumer_dlq_events",
        )
    if "fk_consumer_dlq_events_ingestion_job_id" in dlq_foreign_keys:
        operations.drop_constraint(
            "fk_consumer_dlq_events_ingestion_job_id",
            "consumer_dlq_events",
            type_="foreignkey",
        )
    for table in ("outbox_events", "consumer_dlq_events"):
        columns = {row["name"] for row in inspect(connection).get_columns(table)}
        if "ingestion_job_id" in columns:
            operations.drop_column(table, "ingestion_job_id")


def test_migration_backfills_only_unique_correlation_owner_and_enforces_fk(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        head_schema = connection.begin_nested()
        operations = _bind_operations(migration, connection)
        _normalize_to_previous_revision(operations, connection)
        evidence_columns, evidence_values = transaction_ingestion_job_insert_fragments(connection)
        for job_id, correlation_id in (
            ("job-unique", "corr-unique"),
            ("job-shared-1", "corr-shared"),
            ("job-shared-2", "corr-shared"),
        ):
            connection.execute(
                text(
                    f"""
                    INSERT INTO ingestion_jobs (
                        job_id, endpoint, entity_type, status, accepted_count,
                        correlation_id, request_id, trace_id{evidence_columns}
                    ) VALUES (
                        :job_id, '/ingest/transactions', 'transaction', 'queued', 1,
                        :correlation_id, :job_id, :job_id{evidence_values}
                    )
                    """
                ),
                {
                    "job_id": job_id,
                    "correlation_id": correlation_id,
                    "tenant_id": TEST_TENANT_ID,
                },
            )
        for event_id, correlation_id in (
            ("dlq-unique", "corr-unique"),
            ("dlq-shared", "corr-shared"),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO consumer_dlq_events (
                        event_id, original_topic, consumer_group, dlq_topic,
                        error_reason_code, error_reason, correlation_id
                    ) VALUES (
                        :event_id, 'transactions.raw.received', 'persistence-service-group',
                        'dlq.persistence_service', 'PERSISTENCE_TIMEOUT', 'timed out',
                        :correlation_id
                    )
                    """
                ),
                {"event_id": event_id, "correlation_id": correlation_id},
            )
        for aggregate_id, status, correlation_id in (
            ("outbox-pending-unique", "PENDING", "corr-unique"),
            ("outbox-failed-unique", "FAILED", "corr-unique"),
            ("outbox-pending-shared", "PENDING", "corr-shared"),
            ("outbox-processed-unique", "PROCESSED", "corr-unique"),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO outbox_events (
                        aggregate_type, aggregate_id, partition_key, event_type,
                        payload, topic, status, correlation_id, retry_count, created_at
                    ) VALUES (
                        'transaction', :aggregate_id, :aggregate_id, 'TransactionPersisted',
                        CAST('{}' AS json), 'transactions.persisted', :status, :correlation_id,
                        0, now()
                    )
                    """
                ),
                {
                    "aggregate_id": aggregate_id,
                    "status": status,
                    "correlation_id": correlation_id,
                },
            )

        migration["upgrade"]()
        owners = dict(
            connection.execute(
                text(
                    """
                    SELECT event_id, ingestion_job_id
                    FROM consumer_dlq_events
                    WHERE event_id IN ('dlq-unique', 'dlq-shared')
                    """
                )
            ).all()
        )
        assert owners == {
            "dlq-unique": "job-unique",
            "dlq-shared": None,
        }
        outbox_owners = dict(
            connection.execute(
                text(
                    """
                    SELECT aggregate_id, ingestion_job_id
                    FROM outbox_events
                    WHERE aggregate_id LIKE 'outbox-%'
                    """
                )
            ).all()
        )
        assert outbox_owners == {
            "outbox-pending-unique": "job-unique",
            "outbox-failed-unique": "job-unique",
            "outbox-pending-shared": None,
            "outbox-processed-unique": None,
        }

        savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    UPDATE consumer_dlq_events
                    SET ingestion_job_id = 'job-does-not-exist'
                    WHERE event_id = 'dlq-shared'
                    """
                )
            )
        savepoint.rollback()

        dlq_indexes = {
            row["name"] for row in inspect(connection).get_indexes("consumer_dlq_events")
        }
        replay_indexes = {
            row["name"] for row in inspect(connection).get_indexes("consumer_dlq_replay_audit")
        }
        assert "ix_consumer_dlq_events_job_observed_id" in dlq_indexes
        assert "ix_consumer_dlq_replay_audit_job_requested_id" in replay_indexes

        migration["downgrade"]()
        assert "ingestion_job_id" not in {
            row["name"] for row in inspect(connection).get_columns("consumer_dlq_events")
        }
        migration["upgrade"]()
        head_schema.rollback()
