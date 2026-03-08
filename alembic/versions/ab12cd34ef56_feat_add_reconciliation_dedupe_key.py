"""feat add financial reconciliation dedupe key

Revision ID: ab12cd34ef56
Revises: f9b0c1d2e3f4
Create Date: 2026-03-08 13:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, None] = "f9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "financial_reconciliation_runs",
        sa.Column("dedupe_key", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_financial_reconciliation_runs_dedupe_key"),
        "financial_reconciliation_runs",
        ["dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_financial_reconciliation_runs_dedupe_key"),
        table_name="financial_reconciliation_runs",
    )
    op.drop_column("financial_reconciliation_runs", "dedupe_key")
