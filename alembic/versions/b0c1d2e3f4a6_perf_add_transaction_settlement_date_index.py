"""perf add transaction settlement date index

Revision ID: b0c1d2e3f4a6
Revises: a0b1c2d3e4f5
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b0c1d2e3f4a6"
down_revision: str | Sequence[str] | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_txn_port_settlement_date_id",
        "transactions",
        ["portfolio_id", "settlement_date", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_txn_port_settlement_date_id", table_name="transactions")
