"""perf: add DLQ operations composite query indexes

Revision ID: c8d9e0f1a2b3
Revises: b7e8f9a0b1c2
Create Date: 2026-03-03 16:10:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_consumer_dlq_events_group_topic_observed_at",
        "consumer_dlq_events",
        ["consumer_group", "original_topic", "observed_at"],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_path_status_requested_at",
        "consumer_dlq_replay_audit",
        ["recovery_path", "replay_status", "requested_at"],
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_fingerprint_status_path",
        "consumer_dlq_replay_audit",
        ["replay_fingerprint", "replay_status", "recovery_path", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_consumer_dlq_replay_audit_fingerprint_status_path",
        table_name="consumer_dlq_replay_audit",
    )
    op.drop_index(
        "ix_consumer_dlq_replay_audit_path_status_requested_at",
        table_name="consumer_dlq_replay_audit",
    )
    op.drop_index(
        "ix_consumer_dlq_events_group_topic_observed_at",
        table_name="consumer_dlq_events",
    )

