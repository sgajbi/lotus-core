"""Add calculation lineage to FIFO and AVCO state ledgers.

Revision ID: c138b2c3d50b
Revises: c137b2c3d50a
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c138b2c3d50b"
down_revision: str | Sequence[str] | None = "c137b2c3d50a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "position_lot_state",
        sa.Column("calculation_lineage", sa.JSON(none_as_null=True), nullable=True),
    )
    op.add_column(
        "average_cost_pool_state",
        sa.Column("calculation_lineage", sa.JSON(none_as_null=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("average_cost_pool_state", "calculation_lineage")
    op.drop_column("position_lot_state", "calculation_lineage")
