"""add durable average cost pool state

Revision ID: c106b2c3d4eb
Revises: c105b2c3d4ea
Create Date: 2026-07-10 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c106b2c3d4eb"
down_revision: str | Sequence[str] | None = "c105b2c3d4ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "average_cost_pool_state",
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("instrument_id", sa.String(), nullable=False),
        sa.Column("representative_source_transaction_id", sa.String(), nullable=True),
        sa.Column("pool_quantity", sa.Numeric(18, 10), nullable=False),
        sa.Column("pool_cost_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("pool_cost_base", sa.Numeric(18, 10), nullable=False),
        sa.Column("state_version", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pool_quantity >= 0",
            name="ck_average_cost_pool_state_quantity_nonnegative",
        ),
        sa.CheckConstraint(
            "pool_cost_local >= 0",
            name="ck_average_cost_pool_state_local_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "pool_cost_base >= 0",
            name="ck_average_cost_pool_state_base_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "pool_quantity = 0 OR representative_source_transaction_id IS NOT NULL",
            name="ck_average_cost_pool_state_positive_source",
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.ForeignKeyConstraint(
            ["representative_source_transaction_id"],
            ["transactions.transaction_id"],
        ),
        sa.PrimaryKeyConstraint("portfolio_id", "security_id"),
    )
    op.create_index(
        "ix_average_cost_pool_state_updated_key",
        "average_cost_pool_state",
        [sa.text("updated_at DESC"), "portfolio_id", "security_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_average_cost_pool_state_updated_key",
        table_name="average_cost_pool_state",
    )
    op.drop_table("average_cost_pool_state")
