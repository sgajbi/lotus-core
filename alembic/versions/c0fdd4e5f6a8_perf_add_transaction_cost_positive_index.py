"""Add positive transaction-cost evidence support index.

Revision ID: c0fdd4e5f6a8
Revises: c0fcd4e5f6a7
Create Date: 2026-05-31 15:35:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0fdd4e5f6a8"
down_revision = "c0fcd4e5f6a7"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_txn_costs_positive_txn_id"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "transaction_costs",
        ["transaction_id"],
        unique=False,
        postgresql_where=sa.text("amount > 0"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="transaction_costs")
