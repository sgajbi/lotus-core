"""perf add normalized fx rate lookup index

Revision ID: 8a9b0c1d2e3f
Revises: 7f8a9b0c1d2e
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8a9b0c1d2e3f"
down_revision: str | Sequence[str] | None = "7f8a9b0c1d2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_fx_rates_normalized_pair_rate_date",
        "fx_rates",
        [
            sa.text("upper(trim(from_currency))"),
            sa.text("upper(trim(to_currency))"),
            sa.text("rate_date DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fx_rates_normalized_pair_rate_date",
        table_name="fx_rates",
    )
