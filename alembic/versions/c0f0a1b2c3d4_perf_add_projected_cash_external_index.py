"""Add projected external cash settlement support index.

Revision ID: c0f0a1b2c3d4
Revises: c0e9f0a1b2c3
Create Date: 2026-05-29 10:05:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0f0a1b2c3d4"
down_revision = "c0e9f0a1b2c3"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_txn_projected_cash_external_port_settle_txn_date_id"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "transactions",
        [
            "portfolio_id",
            "settlement_date",
            "transaction_date",
            "id",
        ],
        unique=False,
        postgresql_where=sa.text(
            "transaction_type IN ('DEPOSIT', 'WITHDRAWAL') AND settlement_date IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="transactions")
