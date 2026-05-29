"""perf: add normalized instrument lookup index

Revision ID: c0e0f1a2b3c4
Revises: c0d9e0f1a2b3
Create Date: 2026-05-29 10:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c0d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_instruments_norm_security_id",
        "instruments",
        [sa.text("trim(security_id)")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_instruments_norm_security_id", table_name="instruments")
