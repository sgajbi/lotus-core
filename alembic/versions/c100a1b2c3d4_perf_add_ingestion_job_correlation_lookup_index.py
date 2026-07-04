"""perf: add ingestion job correlation lookup index

Revision ID: c100a1b2c3d4
Revises: c1009d0e1f2a3
Create Date: 2026-07-04 19:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c100a1b2c3d4"
down_revision: Union[str, None] = "c1009d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_ingestion_jobs_correlation_status_id",
        "ingestion_jobs",
        ["correlation_id", "status", sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_correlation_status_id", table_name="ingestion_jobs")
