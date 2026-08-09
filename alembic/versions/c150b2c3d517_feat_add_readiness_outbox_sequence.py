"""Add exact-scope readiness sequence authority to valuation jobs.

Revision ID: c150b2c3d517
Revises: c149b2c3d516
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c150b2c3d517"
down_revision: str | Sequence[str] | None = "c149b2c3d516"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the latest readiness outbox sequence covered by valuation claim."""

    op.add_column(
        "portfolio_valuation_jobs",
        sa.Column(
            "claimed_readiness_outbox_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    """Remove exact-scope readiness sequence authority."""

    op.drop_column("portfolio_valuation_jobs", "claimed_readiness_outbox_id")
