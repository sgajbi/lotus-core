"""Add calculation lineage to the durable position-history ledger.

Revision ID: c134b2c3d507
Revises: c133b2c3d506
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c134b2c3d507"
down_revision: str | Sequence[str] | None = "c133b2c3d506"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable lineage without fabricating evidence for legacy rows."""

    op.add_column(
        "position_history",
        sa.Column(
            "calculation_lineage",
            sa.JSON(none_as_null=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove lineage without changing position-history economics."""

    op.drop_column("position_history", "calculation_lineage")
