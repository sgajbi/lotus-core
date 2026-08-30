"""Index the portfolio-scoped exact transaction lookup.

Revision ID: c164b2c3d52b
Revises: c163b2c3d52a
Create Date: 2026-08-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c164b2c3d52b"
down_revision: str | Sequence[str] | None = "c163b2c3d52a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_transactions_portfolio_transaction_id"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            _INDEX_NAME,
            "transactions",
            ["portfolio_id", "transaction_id"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            _INDEX_NAME,
            table_name="transactions",
            postgresql_concurrently=True,
            if_exists=True,
        )
