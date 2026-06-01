"""Add benchmark composition latest support index.

Revision ID: c0fcc3d4e5f6
Revises: c0fbb2c3d4e5
Create Date: 2026-05-31 15:55:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0fcc3d4e5f6"
down_revision = "c0fbb2c3d4e5"
branch_labels = None
depends_on = None


BENCHMARK_COMPOSITION_LATEST_INDEX = "ix_bench_comp_benchmark_index_eff"


def upgrade() -> None:
    op.create_index(
        BENCHMARK_COMPOSITION_LATEST_INDEX,
        "benchmark_composition_series",
        [
            "benchmark_id",
            "index_id",
            sa.text("composition_effective_from DESC"),
            "composition_effective_to",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        BENCHMARK_COMPOSITION_LATEST_INDEX,
        table_name="benchmark_composition_series",
    )
