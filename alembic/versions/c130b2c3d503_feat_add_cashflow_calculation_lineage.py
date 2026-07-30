"""Add calculation lineage to the durable cashflow ledger.

Revision ID: c130b2c3d503
Revises: c129b2c3d502
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c130b2c3d503"
down_revision: str | Sequence[str] | None = "c129b2c3d502"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add additive lineage while preserving legacy cashflow rows."""

    op.add_column(
        "cashflows",
        sa.Column(
            "calculation_lineage",
            sa.JSON(none_as_null=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove cashflow calculation lineage without changing cashflow economics."""

    op.drop_column("cashflows", "calculation_lineage")
