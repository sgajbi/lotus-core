"""Normalize analytics export status values.

Revision ID: c0e4f5a6b7c8
Revises: c0e3f4a5b6c7
Create Date: 2026-05-29 08:35:00.000000
"""

from alembic import op

revision = "c0e4f5a6b7c8"
down_revision = "c0e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE analytics_export_jobs SET status = lower(trim(status)) WHERE status IS NOT NULL"
    )


def downgrade() -> None:
    # Status canonicalization is data cleanup and is intentionally irreversible.
    pass
