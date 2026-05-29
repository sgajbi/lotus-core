"""Add portfolio manager book membership index.

Revision ID: c0e6f7a8b9c0
Revises: c0e5f6a7b8c9
Create Date: 2026-05-29 08:55:00.000000
"""

from alembic import op

revision = "c0e6f7a8b9c0"
down_revision = "c0e5f6a7b8c9"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_portfolios_advisor_status_open_close_portfolio"


def upgrade() -> None:
    op.execute("UPDATE portfolios SET status = upper(trim(status)) WHERE status IS NOT NULL")
    op.create_index(
        INDEX_NAME,
        "portfolios",
        ["advisor_id", "status", "open_date", "close_date", "portfolio_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="portfolios")
    # Status canonicalization is data cleanup and is intentionally irreversible.
