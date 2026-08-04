"""Add governed external destination authority to transaction records.

Revision ID: c148b2c3d515
Revises: c147b2c3d514
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c148b2c3d515"
down_revision: str | Sequence[str] | None = "c147b2c3d514"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add an optional opaque external destination without rewriting existing transactions."""

    op.add_column(
        "transactions",
        sa.Column("external_destination_reference", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Remove external destination authority."""

    op.drop_column("transactions", "external_destination_reference")
