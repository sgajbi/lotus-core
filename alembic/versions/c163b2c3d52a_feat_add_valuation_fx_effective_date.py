"""Preserve the FX effective date used by position valuations.

Revision ID: c163b2c3d52a
Revises: c162b2c3d529
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c163b2c3d52a"
down_revision: str | Sequence[str] | None = "c162b2c3d529"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_position_snapshots",
        sa.Column("valuation_fx_rate_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_position_snapshots", "valuation_fx_rate_date")
