"""Add DLQ correlation diagnostics.

Revision ID: c1007b8c9d0e1
Revises: c1006a7b8c9d0
Create Date: 2026-06-30 18:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1007b8c9d0e1"
down_revision: str | Sequence[str] | None = "c1006a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "consumer_dlq_events",
        sa.Column("correlation_missing_reason", sa.String(), nullable=True),
    )
    op.add_column(
        "consumer_dlq_events",
        sa.Column("alternate_lookup_key", sa.String(), nullable=True),
    )
    op.add_column(
        "consumer_dlq_replay_audit",
        sa.Column("correlation_missing_reason", sa.String(), nullable=True),
    )
    op.add_column(
        "consumer_dlq_replay_audit",
        sa.Column("alternate_lookup_key", sa.String(), nullable=True),
    )

    op.execute(
        """
        UPDATE consumer_dlq_events
        SET correlation_missing_reason = 'message_correlation_id_absent',
            alternate_lookup_key = 'consumer_dlq|topic=' || original_topic
                || '|group=' || consumer_group
                || '|dlq=' || dlq_topic
                || '|key=' || coalesce(original_key, 'unkeyed')
                || '|event=' || event_id
        WHERE (correlation_id IS NULL OR trim(correlation_id) = '')
          AND correlation_missing_reason IS NULL
        """
    )
    op.execute(
        """
        UPDATE consumer_dlq_replay_audit
        SET correlation_missing_reason = 'replay_correlation_id_absent',
            alternate_lookup_key = 'replay_audit|event=' || event_id
                || '|job=' || coalesce(job_id, 'unmapped')
                || '|endpoint=' || coalesce(endpoint, 'unmapped')
                || '|status=' || replay_status
        WHERE (correlation_id IS NULL OR trim(correlation_id) = '')
          AND correlation_missing_reason IS NULL
        """
    )

    op.create_index(
        "ix_consumer_dlq_events_alternate_lookup_key",
        "consumer_dlq_events",
        ["alternate_lookup_key"],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_alternate_lookup_key",
        "consumer_dlq_replay_audit",
        ["alternate_lookup_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_consumer_dlq_replay_audit_alternate_lookup_key",
        table_name="consumer_dlq_replay_audit",
    )
    op.drop_index(
        "ix_consumer_dlq_events_alternate_lookup_key",
        table_name="consumer_dlq_events",
    )
    op.drop_column("consumer_dlq_replay_audit", "alternate_lookup_key")
    op.drop_column("consumer_dlq_replay_audit", "correlation_missing_reason")
    op.drop_column("consumer_dlq_events", "alternate_lookup_key")
    op.drop_column("consumer_dlq_events", "correlation_missing_reason")
