"""add FIFO lot restoration ordering index

Revision ID: c105b2c3d4ea
Revises: c104b2c3d4e9
Create Date: 2026-07-10 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c105b2c3d4ea"
down_revision: str | Sequence[str] | None = "c104b2c3d4e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_txn_norm_port_sec_date_qty_id",
        "transactions",
        [
            sa.text("trim(portfolio_id)"),
            sa.text("trim(security_id)"),
            "transaction_date",
            sa.text("quantity DESC"),
            "transaction_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_txn_norm_port_sec_date_qty_id", table_name="transactions")
