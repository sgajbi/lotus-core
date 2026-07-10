"""add allocated corporate action cash basis

Revision ID: c103b2c3d4e8
Revises: c102b2c3d4e7
Create Date: 2026-07-10 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c103b2c3d4e8"
down_revision: Union[str, None] = "c102b2c3d4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("allocated_cost_basis_local", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("allocated_cost_basis_base", sa.Numeric(18, 10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "allocated_cost_basis_base")
    op.drop_column("transactions", "allocated_cost_basis_local")
