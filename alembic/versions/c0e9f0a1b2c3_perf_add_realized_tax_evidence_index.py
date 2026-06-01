"""Add realized tax evidence support index.

Revision ID: c0e9f0a1b2c3
Revises: c0e8f9a0b1c2
Create Date: 2026-05-29 09:45:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0e9f0a1b2c3"
down_revision = "c0e8f9a0b1c2"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_txn_realized_tax_evidence_port_currency_date_txn"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "transactions",
        [
            "portfolio_id",
            "currency",
            "transaction_date",
            "transaction_id",
        ],
        unique=False,
        postgresql_where=sa.text(
            "withholding_tax_amount IS NOT NULL OR other_interest_deductions_amount IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="transactions")
