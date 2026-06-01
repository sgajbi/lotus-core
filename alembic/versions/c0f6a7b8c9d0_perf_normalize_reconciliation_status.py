"""Normalize reconciliation support lifecycle values.

Revision ID: c0f6a7b8c9d0
Revises: c0f5a6b7c8d9
Create Date: 2026-05-31 13:15:00.000000
"""

from alembic import op

revision = "c0f6a7b8c9d0"
down_revision = "c0f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE financial_reconciliation_runs "
        "SET status = upper(trim(status)) "
        "WHERE status IS NOT NULL"
    )
    op.execute(
        "UPDATE financial_reconciliation_findings "
        "SET severity = upper(trim(severity)) "
        "WHERE severity IS NOT NULL"
    )


def downgrade() -> None:
    # Reconciliation lifecycle and severity canonicalization is intentionally irreversible.
    pass
