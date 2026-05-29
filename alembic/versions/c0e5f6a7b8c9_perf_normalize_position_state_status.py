"""Normalize position state status values.

Revision ID: c0e5f6a7b8c9
Revises: c0e4f5a6b7c8
Create Date: 2026-05-29 08:45:00.000000
"""

from alembic import op

revision = "c0e5f6a7b8c9"
down_revision = "c0e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE position_state SET status = upper(trim(status)) WHERE status IS NOT NULL")


def downgrade() -> None:
    # Status canonicalization is data cleanup and is intentionally irreversible.
    pass
