"""Add calculation lineage to portfolio timeseries.

Revision ID: c137b2c3d50a
Revises: c136b2c3d509
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c137b2c3d50a"
down_revision: str | Sequence[str] | None = "c136b2c3d509"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portfolio_timeseries",
        sa.Column("calculation_lineage", sa.JSON(none_as_null=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_timeseries", "calculation_lineage")
