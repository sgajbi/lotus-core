"""Add calculation lineage to position timeseries.

Revision ID: c136b2c3d509
Revises: c135b2c3d508
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c136b2c3d509"
down_revision: str | Sequence[str] | None = "c135b2c3d508"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "position_timeseries",
        sa.Column("calculation_lineage", sa.JSON(none_as_null=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("position_timeseries", "calculation_lineage")
