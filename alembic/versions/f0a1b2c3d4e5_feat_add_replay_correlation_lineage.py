"""feat: add replay correlation lineage

Revision ID: f0a1b2c3d4e5
Revises: e4f5a6b7c8d9
Create Date: 2026-03-12 23:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instrument_reprocessing_state",
        sa.Column("correlation_id", sa.String(), nullable=True),
    )
    op.add_column(
        "reprocessing_jobs",
        sa.Column("correlation_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reprocessing_jobs", "correlation_id")
    op.drop_column("instrument_reprocessing_state", "correlation_id")
