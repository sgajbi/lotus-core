"""Add cashflow latest portfolio support index.

Revision ID: c0faa1b2c3d4
Revises: c0f9a0b1c2d3
Create Date: 2026-05-31 14:50:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0faa1b2c3d4"
down_revision = "c0f9a0b1c2d3"
branch_labels = None
depends_on = None


CASHFLOW_LATEST_PORTFOLIO_INDEX = "ix_cashflows_port_txn_epoch_id"


def upgrade() -> None:
    op.create_index(
        CASHFLOW_LATEST_PORTFOLIO_INDEX,
        "cashflows",
        [
            "portfolio_id",
            "transaction_id",
            sa.text("epoch DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        CASHFLOW_LATEST_PORTFOLIO_INDEX,
        table_name="cashflows",
    )
