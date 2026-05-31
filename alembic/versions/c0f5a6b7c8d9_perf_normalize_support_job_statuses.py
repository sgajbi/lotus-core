"""Normalize support job lifecycle statuses.

Revision ID: c0f5a6b7c8d9
Revises: c0f4a5b6c7d8
Create Date: 2026-05-31 12:55:00.000000
"""

from alembic import op

revision = "c0f5a6b7c8d9"
down_revision = "c0f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE portfolio_valuation_jobs SET status = upper(trim(status)) WHERE status IS NOT NULL"
    )
    op.execute(
        "UPDATE portfolio_aggregation_jobs "
        "SET status = upper(trim(status)) "
        "WHERE status IS NOT NULL"
    )
    op.execute("UPDATE reprocessing_jobs SET status = upper(trim(status)) WHERE status IS NOT NULL")


def downgrade() -> None:
    # Support job lifecycle status canonicalization is intentionally irreversible.
    pass
