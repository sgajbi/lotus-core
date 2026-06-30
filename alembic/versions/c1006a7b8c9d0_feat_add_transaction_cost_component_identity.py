"""Add transaction-cost component identity.

Revision ID: c1006a7b8c9d0
Revises: c1005f6a7b8c9
Create Date: 2026-06-30 12:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1006a7b8c9d0"
down_revision: str | Sequence[str] | None = "c1005f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEX_NAME = "uq_transaction_costs_component_identity"


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM transaction_costs AS duplicate
        USING (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY transaction_id, lower(trim(fee_type)), upper(trim(currency))
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
                ) AS component_rank
            FROM transaction_costs
        ) AS ranked
        WHERE duplicate.id = ranked.id
          AND ranked.component_rank > 1
        """
    )
    op.create_index(
        INDEX_NAME,
        "transaction_costs",
        [
            "transaction_id",
            sa.text("lower(trim(fee_type))"),
            sa.text("upper(trim(currency))"),
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="transaction_costs")
