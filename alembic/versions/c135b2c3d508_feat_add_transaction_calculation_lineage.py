"""Add calculated-output lineage to the canonical transaction ledger.

Revision ID: c135b2c3d508
Revises: c134b2c3d507
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c135b2c3d508"
down_revision: str | Sequence[str] | None = "c134b2c3d507"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable lineage without inventing evidence for historical transactions."""

    op.add_column(
        "transactions",
        sa.Column(
            "calculation_lineage",
            sa.JSON(none_as_null=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove lineage without changing canonical transaction economics."""

    op.drop_column("transactions", "calculation_lineage")
