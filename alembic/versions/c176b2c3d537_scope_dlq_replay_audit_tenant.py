"""Scope consumer DLQ and replay-audit evidence to durable tenant authority.

Revision ID: c176b2c3d537
Revises: c175b2c3d536
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c176b2c3d537"
down_revision: str | Sequence[str] | None = "c175b2c3d536"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DLQ = "consumer_dlq_events"
_AUDIT = "consumer_dlq_replay_audit"


def _abort_unattributable(table: str, identity: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE invalid_count bigint; invalid_samples text;
            BEGIN
                SELECT count(*) INTO invalid_count FROM {table} WHERE tenant_id IS NULL;
                SELECT string_agg(value, ', ' ORDER BY value) INTO invalid_samples
                FROM (SELECT {identity}::text AS value FROM {table}
                      WHERE tenant_id IS NULL ORDER BY {identity} LIMIT 20) AS samples;
                IF invalid_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            '{table} tenant cutover found %s unattributable row(s); sample: %s',
                            invalid_count, coalesce(invalid_samples, '<none>')
                        ),
                        HINT = 'repair only from a durable owning ingestion job; '
                            || 'never invent a tenant';
                END IF;
            END $$
            """
        )
    )


def _abort_unknown_audit_jobs() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE invalid_count bigint; invalid_samples text;
            BEGIN
                SELECT count(*) INTO invalid_count
                FROM consumer_dlq_replay_audit AS audit
                WHERE audit.job_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM ingestion_jobs AS job WHERE job.job_id = audit.job_id
                  );
                SELECT string_agg(replay_id, ', ' ORDER BY replay_id) INTO invalid_samples
                FROM (
                    SELECT audit.replay_id
                    FROM consumer_dlq_replay_audit AS audit
                    WHERE audit.job_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM ingestion_jobs AS job WHERE job.job_id = audit.job_id
                      )
                    ORDER BY audit.replay_id LIMIT 20
                ) AS samples;
                IF invalid_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'consumer_dlq_replay_audit tenant cutover found %s row(s) with '
                                || 'an unknown ingestion job; sample: %s',
                            invalid_count, coalesce(invalid_samples, '<none>')
                        ),
                        HINT = 'repair the durable job reference or clear it only with '
                            || 'governed evidence before retrying';
                END IF;
            END $$
            """
        )
    )


def upgrade() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute(
        sa.text(
            "LOCK TABLE consumer_dlq_events, consumer_dlq_replay_audit, ingestion_jobs "
            "IN ACCESS EXCLUSIVE MODE"
        )
    )
    op.add_column(_DLQ, sa.Column("tenant_id", sa.String(length=128), nullable=True))
    op.add_column(_AUDIT, sa.Column("tenant_id", sa.String(length=128), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE consumer_dlq_events AS dlq
            SET tenant_id = job.tenant_id
            FROM ingestion_jobs AS job
            WHERE dlq.ingestion_job_id = job.job_id
            """
        )
    )
    _abort_unattributable(_DLQ, "event_id")
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE conflict_count bigint; conflict_samples text;
            BEGIN
                SELECT count(*) INTO conflict_count
                FROM consumer_dlq_replay_audit AS audit
                JOIN consumer_dlq_events AS dlq ON dlq.event_id = audit.event_id
                JOIN ingestion_jobs AS job ON job.job_id = audit.job_id
                WHERE job.tenant_id IS DISTINCT FROM dlq.tenant_id;
                SELECT string_agg(replay_id, ', ' ORDER BY replay_id) INTO conflict_samples
                FROM (
                    SELECT audit.replay_id
                    FROM consumer_dlq_replay_audit AS audit
                    JOIN consumer_dlq_events AS dlq ON dlq.event_id = audit.event_id
                    JOIN ingestion_jobs AS job ON job.job_id = audit.job_id
                    WHERE job.tenant_id IS DISTINCT FROM dlq.tenant_id
                    ORDER BY audit.replay_id LIMIT 20
                ) AS samples;
                IF conflict_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'consumer_dlq_replay_audit tenant cutover found %s '
                                || 'conflicting owner(s); sample: %s',
                            conflict_count, coalesce(conflict_samples, '<none>')
                        ),
                        HINT = 'reconcile the durable job and DLQ ownership before retrying';
                END IF;
            END $$
            """
        )
    )
    _abort_unknown_audit_jobs()
    op.execute(
        sa.text(
            """
            UPDATE consumer_dlq_replay_audit AS audit
            SET tenant_id = job.tenant_id
            FROM ingestion_jobs AS job
            WHERE audit.job_id = job.job_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE consumer_dlq_replay_audit AS audit
            SET tenant_id = dlq.tenant_id
            FROM consumer_dlq_events AS dlq
            WHERE audit.tenant_id IS NULL AND audit.event_id = dlq.event_id
            """
        )
    )
    _abort_unattributable(_AUDIT, "replay_id")

    op.alter_column(_DLQ, "tenant_id", existing_type=sa.String(length=128), nullable=False)
    op.alter_column(_DLQ, "ingestion_job_id", existing_type=sa.String(), nullable=False)
    op.alter_column(_AUDIT, "tenant_id", existing_type=sa.String(length=128), nullable=False)
    for table in (_DLQ, _AUDIT):
        op.create_check_constraint(
            f"ck_{table}_tenant_id_canonical",
            table,
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' AND char_length(tenant_id) <= 128",
        )

    op.drop_index("ix_consumer_dlq_events_event_id", table_name=_DLQ)
    op.drop_index("ix_consumer_dlq_replay_audit_replay_id", table_name=_AUDIT)
    op.drop_constraint("consumer_dlq_events_event_id_key", _DLQ, type_="unique")
    op.create_unique_constraint(
        "uq_consumer_dlq_events_tenant_event", _DLQ, ["tenant_id", "event_id"]
    )
    op.create_unique_constraint(
        "uq_consumer_dlq_replay_audit_tenant_replay", _AUDIT, ["tenant_id", "replay_id"]
    )
    op.create_unique_constraint(
        "uq_ingestion_jobs_tenant_job_id", "ingestion_jobs", ["tenant_id", "job_id"]
    )
    op.create_foreign_key(
        "fk_consumer_dlq_events_tenant_job",
        _DLQ,
        "ingestion_jobs",
        ["tenant_id", "ingestion_job_id"],
        ["tenant_id", "job_id"],
    )
    op.create_foreign_key(
        "fk_consumer_dlq_replay_audit_tenant_job",
        _AUDIT,
        "ingestion_jobs",
        ["tenant_id", "job_id"],
        ["tenant_id", "job_id"],
    )
    for name, table in (
        ("ix_consumer_dlq_events_group_topic_observed_at", _DLQ),
        ("ix_consumer_dlq_events_job_observed_id", _DLQ),
        ("ix_consumer_dlq_replay_audit_path_status_requested_at", _AUDIT),
        ("ix_consumer_dlq_replay_audit_fingerprint_status_path", _AUDIT),
        ("ix_consumer_dlq_replay_audit_job_requested_id", _AUDIT),
    ):
        op.drop_index(name, table_name=table)
    op.create_index(
        "ix_consumer_dlq_events_group_topic_observed_at",
        _DLQ,
        ["tenant_id", "consumer_group", "original_topic", sa.text("observed_at DESC")],
    )
    op.create_index(
        "ix_consumer_dlq_events_job_observed_id",
        _DLQ,
        ["tenant_id", "ingestion_job_id", sa.text("observed_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_path_status_requested_at",
        _AUDIT,
        ["tenant_id", "recovery_path", "replay_status", sa.text("requested_at DESC")],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_fingerprint_status_path",
        _AUDIT,
        [
            "tenant_id",
            "replay_fingerprint",
            "replay_status",
            "recovery_path",
            sa.text("requested_at DESC"),
        ],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_job_requested_id",
        _AUDIT,
        ["tenant_id", "job_id", sa.text("requested_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute(
        sa.text(
            "LOCK TABLE consumer_dlq_events, consumer_dlq_replay_audit, ingestion_jobs "
            "IN ACCESS EXCLUSIVE MODE"
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE collisions text;
            BEGIN
                SELECT string_agg(identity, ', ' ORDER BY identity) INTO collisions
                FROM (
                    SELECT event_id AS identity FROM consumer_dlq_events
                    GROUP BY event_id HAVING count(*) > 1
                    UNION ALL
                    SELECT replay_id AS identity FROM consumer_dlq_replay_audit
                    GROUP BY replay_id HAVING count(*) > 1
                    LIMIT 20
                ) AS values_with_collisions;
                IF collisions IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'tenant-scoped DLQ/replay identities block downgrade: %s',
                            collisions
                        ),
                        HINT = 'retain this revision or reconcile colliding identifiers '
                            || 'before downgrade';
                END IF;
            END $$
            """
        )
    )
    op.drop_constraint("fk_consumer_dlq_replay_audit_tenant_job", _AUDIT, type_="foreignkey")
    op.drop_constraint("fk_consumer_dlq_events_tenant_job", _DLQ, type_="foreignkey")
    op.drop_constraint("uq_ingestion_jobs_tenant_job_id", "ingestion_jobs", type_="unique")
    op.alter_column(_DLQ, "ingestion_job_id", existing_type=sa.String(), nullable=True)
    for name, table in (
        ("ix_consumer_dlq_events_group_topic_observed_at", _DLQ),
        ("ix_consumer_dlq_events_job_observed_id", _DLQ),
        ("ix_consumer_dlq_replay_audit_path_status_requested_at", _AUDIT),
        ("ix_consumer_dlq_replay_audit_fingerprint_status_path", _AUDIT),
        ("ix_consumer_dlq_replay_audit_job_requested_id", _AUDIT),
    ):
        op.drop_index(name, table_name=table)
    op.drop_constraint("uq_consumer_dlq_events_tenant_event", _DLQ, type_="unique")
    op.drop_constraint("uq_consumer_dlq_replay_audit_tenant_replay", _AUDIT, type_="unique")
    op.create_unique_constraint("consumer_dlq_events_event_id_key", _DLQ, ["event_id"])
    op.create_index("ix_consumer_dlq_events_event_id", _DLQ, ["event_id"], unique=True)
    op.create_index("ix_consumer_dlq_replay_audit_replay_id", _AUDIT, ["replay_id"], unique=True)
    op.create_index(
        "ix_consumer_dlq_events_group_topic_observed_at",
        _DLQ,
        ["consumer_group", "original_topic", sa.text("observed_at DESC")],
    )
    op.create_index(
        "ix_consumer_dlq_events_job_observed_id",
        _DLQ,
        ["ingestion_job_id", sa.text("observed_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_path_status_requested_at",
        _AUDIT,
        ["recovery_path", "replay_status", sa.text("requested_at DESC")],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_fingerprint_status_path",
        _AUDIT,
        ["replay_fingerprint", "replay_status", "recovery_path", sa.text("requested_at DESC")],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_job_requested_id",
        _AUDIT,
        ["job_id", sa.text("requested_at DESC"), sa.text("id DESC")],
    )
    for table in (_AUDIT, _DLQ):
        op.drop_constraint(f"ck_{table}_tenant_id_canonical", table, type_="check")
        op.drop_column(table, "tenant_id")
