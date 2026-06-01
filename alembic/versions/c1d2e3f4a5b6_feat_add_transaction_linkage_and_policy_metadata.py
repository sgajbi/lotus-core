"""feat: add transaction linkage and policy metadata

Revision ID: c1d2e3f4a5b6
Revises: a7d3c9f1e4b2
Create Date: 2026-02-28 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "a7d3c9f1e4b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("economic_event_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("linked_transaction_group_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("calculation_policy_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("calculation_policy_version", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("source_system", sa.String(), nullable=True),
    )

    op.create_index(
        "ix_transactions_economic_event_id",
        "transactions",
        ["economic_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_linked_transaction_group_id",
        "transactions",
        ["linked_transaction_group_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_linked_transaction_group_id", table_name="transactions")
    op.drop_index("ix_transactions_economic_event_id", table_name="transactions")

    op.drop_column("transactions", "source_system")
    op.drop_column("transactions", "calculation_policy_version")
    op.drop_column("transactions", "calculation_policy_id")
    op.drop_column("transactions", "linked_transaction_group_id")
    op.drop_column("transactions", "economic_event_id")
