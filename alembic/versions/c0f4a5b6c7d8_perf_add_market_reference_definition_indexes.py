"""Add market reference definition support indexes.

Revision ID: c0f4a5b6c7d8
Revises: c0f3a4b5c6d7
Create Date: 2026-05-31 12:05:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0f4a5b6c7d8"
down_revision = "c0f3a4b5c6d7"
branch_labels = None
depends_on = None


BENCHMARK_DEFINITION_INDEX = "ix_benchmark_def_active_id_eff"
INDEX_DEFINITION_INDEX = "ix_index_def_active_id_eff"


def upgrade() -> None:
    op.execute(
        "UPDATE benchmark_definitions "
        "SET benchmark_status = lower(trim(benchmark_status)) "
        "WHERE benchmark_status IS NOT NULL"
    )
    op.execute(
        "UPDATE index_definitions "
        "SET index_status = lower(trim(index_status)) "
        "WHERE index_status IS NOT NULL"
    )
    op.create_index(
        BENCHMARK_DEFINITION_INDEX,
        "benchmark_definitions",
        [
            "benchmark_id",
            sa.text("effective_from DESC"),
            "effective_to",
        ],
        unique=False,
        postgresql_where=sa.text("benchmark_status = 'active'"),
    )
    op.create_index(
        INDEX_DEFINITION_INDEX,
        "index_definitions",
        [
            "index_id",
            sa.text("effective_from DESC"),
            "effective_to",
        ],
        unique=False,
        postgresql_where=sa.text("index_status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_DEFINITION_INDEX, table_name="index_definitions")
    op.drop_index(BENCHMARK_DEFINITION_INDEX, table_name="benchmark_definitions")
    # Market/reference lifecycle status canonicalization is intentionally irreversible.
