"""add cost basis processing state

Revision ID: c102b2c3d4e7
Revises: c101b2c3d4e6
Create Date: 2026-07-10 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c102b2c3d4e7"
down_revision: Union[str, None] = "c101b2c3d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cost_basis_processing_state",
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("cost_basis_method", sa.String(), nullable=False),
        sa.Column("latest_transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_dependency_rank", sa.Integer(), nullable=False),
        sa.Column("latest_cash_dependency_rank", sa.Integer(), nullable=False),
        sa.Column("latest_child_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "latest_target_instrument_id",
            sa.String(),
            server_default="",
            nullable=False,
        ),
        sa.Column("latest_quantity", sa.Numeric(18, 10), nullable=False),
        sa.Column("latest_transaction_id", sa.String(), nullable=False),
        sa.Column("engine_state_version", sa.String(), nullable=False),
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
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("portfolio_id", "security_id"),
    )
    op.create_index(
        "ix_cost_basis_processing_state_updated_key",
        "cost_basis_processing_state",
        [sa.text("updated_at DESC"), "portfolio_id", "security_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cost_basis_processing_state_updated_key",
        table_name="cost_basis_processing_state",
    )
    op.drop_table("cost_basis_processing_state")
