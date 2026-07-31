"""Add durable ingestion-job ownership to event lineage.

Revision ID: c133b2c3d506
Revises: c132b2c3d505
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c133b2c3d506"
down_revision: str | Sequence[str] | None = "c132b2c3d505"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DLQ_TABLE = "consumer_dlq_events"
_OUTBOX_TABLE = "outbox_events"
_REPLAY_TABLE = "consumer_dlq_replay_audit"
_DLQ_JOB_INDEX = "ix_consumer_dlq_events_job_observed_id"
_REPLAY_JOB_INDEX = "ix_consumer_dlq_replay_audit_job_requested_id"
_DLQ_JOB_FK = "fk_consumer_dlq_events_ingestion_job_id"


def upgrade() -> None:
    op.add_column(_DLQ_TABLE, sa.Column("ingestion_job_id", sa.String(), nullable=True))
    op.add_column(_OUTBOX_TABLE, sa.Column("ingestion_job_id", sa.String(), nullable=True))

    # Preserve compatible legacy evidence only when correlation maps to exactly one job.
    # Ambiguous correlation reuse deliberately remains ownerless and therefore fail-closed.
    op.execute(
        """
        WITH unique_owners AS (
            SELECT dlq.id AS dlq_id, min(job.job_id) AS ingestion_job_id
            FROM consumer_dlq_events AS dlq
            JOIN ingestion_jobs AS job
              ON job.correlation_id = dlq.correlation_id
            WHERE dlq.correlation_id IS NOT NULL
              AND btrim(dlq.correlation_id) <> ''
            GROUP BY dlq.id
            HAVING count(*) = 1
        )
        UPDATE consumer_dlq_events AS dlq
        SET ingestion_job_id = owner.ingestion_job_id
        FROM unique_owners AS owner
        WHERE dlq.id = owner.dlq_id
          AND dlq.ingestion_job_id IS NULL
        """
    )
    op.create_foreign_key(
        _DLQ_JOB_FK,
        _DLQ_TABLE,
        "ingestion_jobs",
        ["ingestion_job_id"],
        ["job_id"],
        postgresql_not_valid=True,
    )
    op.execute(f'ALTER TABLE "{_DLQ_TABLE}" VALIDATE CONSTRAINT "{_DLQ_JOB_FK}"')
    op.create_index(
        _DLQ_JOB_INDEX,
        _DLQ_TABLE,
        ["ingestion_job_id", sa.text("observed_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        _REPLAY_JOB_INDEX,
        _REPLAY_TABLE,
        ["job_id", sa.text("requested_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(_REPLAY_JOB_INDEX, table_name=_REPLAY_TABLE)
    op.drop_index(_DLQ_JOB_INDEX, table_name=_DLQ_TABLE)
    op.drop_constraint(_DLQ_JOB_FK, _DLQ_TABLE, type_="foreignkey")
    op.drop_column(_OUTBOX_TABLE, "ingestion_job_id")
    op.drop_column(_DLQ_TABLE, "ingestion_job_id")
