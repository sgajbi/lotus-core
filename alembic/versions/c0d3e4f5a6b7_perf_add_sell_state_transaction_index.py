"""perf add sell state transaction index

Revision ID: c0d3e4f5a6b7
Revises: c0d2e3f4a5b6
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c0d3e4f5a6b7"
down_revision: str | Sequence[str] | None = "c0d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_txn_port_norm_sec_type_date_id",
        "transactions",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            "transaction_type",
            sa.text("transaction_date DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_txn_port_norm_sec_type_date_id", table_name="transactions")
