"""Preserve source corrections that supersede in-flight valuation work.

Revision ID: c114b2c3d4f3
Revises: c113b2c3d4f2
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c114b2c3d4f3"
down_revision: str | None = "c113b2c3d4f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a durable single-row fence for superseded valuation claims."""

    op.add_column(
        "portfolio_valuation_jobs",
        sa.Column(
            "requeue_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Remove the in-flight valuation supersession fence."""

    op.drop_column("portfolio_valuation_jobs", "requeue_requested")
