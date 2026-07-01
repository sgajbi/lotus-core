"""Add outbox recovery audit table.

Revision ID: c1008d9e0f1a2
Revises: c1007b8c9d0e1
Create Date: 2026-07-01 08:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1008d9e0f1a2"
down_revision: str | Sequence[str] | None = "c1007b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_recovery_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("outbox_id", sa.Integer(), nullable=False),
        sa.Column("recovery_action", sa.String(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("prior_status", sa.String(), nullable=False),
        sa.Column("new_status", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("outcome_message", sa.String(), nullable=True),
        sa.Column("prior_retry_count", sa.Integer(), nullable=False),
        sa.Column("prior_last_failure_reason_code", sa.String(), nullable=True),
        sa.Column("prior_last_failure_category", sa.String(), nullable=True),
        sa.Column("prior_last_failure_message", sa.String(), nullable=True),
        sa.Column("prior_last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["outbox_id"], ["outbox_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_outbox_recovery_audit_outbox_id"),
        "outbox_recovery_audit",
        ["outbox_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_recovery_audit_correlation_id"),
        "outbox_recovery_audit",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_recovery_audit_outcome"),
        "outbox_recovery_audit",
        ["outcome"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_recovery_audit_outbox_requested_at",
        "outbox_recovery_audit",
        ["outbox_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_recovery_audit_outcome_requested_at",
        "outbox_recovery_audit",
        ["outcome", "requested_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_recovery_audit_outcome_requested_at",
        table_name="outbox_recovery_audit",
    )
    op.drop_index(
        "ix_outbox_recovery_audit_outbox_requested_at",
        table_name="outbox_recovery_audit",
    )
    op.drop_index(op.f("ix_outbox_recovery_audit_outcome"), table_name="outbox_recovery_audit")
    op.drop_index(
        op.f("ix_outbox_recovery_audit_correlation_id"),
        table_name="outbox_recovery_audit",
    )
    op.drop_index(op.f("ix_outbox_recovery_audit_outbox_id"), table_name="outbox_recovery_audit")
    op.drop_table("outbox_recovery_audit")
