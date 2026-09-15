"""Remove quadratic selected-cashflow self-join without changing source cuts.

Revision ID: c170b2c3d531
Revises: c169b2c3d530
Create Date: 2026-09-16

Replace only the refresh function. Existing rows, canonical digest inputs,
chronology, statement batching, deferred flush and durable portfolio locks
remain unchanged; old and new runtimes consume the same source-cut schema.
"""

import runpy
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "c170b2c3d531"
down_revision: str | Sequence[str] | None = "c169b2c3d530"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREVIOUS = "c169b2c3d530_feat_add_portfolio_cashflow_source_cut.py"
_CREATE = "CREATE FUNCTION refresh_portfolio_cashflow_source_cut(target_portfolio_id text)"
_ROW_FIELDS = "                id\n                FROM selected_cashflows"
_SELF_JOIN = (
    "FROM selected_cashflows\n"
    "                LEFT JOIN cashflow_rows USING (transaction_id, epoch, id)"
)


def _refresh_sql(*, linear: bool) -> str:
    """Pin the unchanged historical contract and refuse unexpected rewrite premises."""
    previous = runpy.run_path(str(Path(__file__).with_name(_PREVIOUS)))
    sql = previous["_refresh_function_sql"]()
    required_fragments = (_CREATE, _ROW_FIELDS, _SELF_JOIN) if linear else (_CREATE,)
    for fragment in required_fragments:
        if sql.count(fragment) != 1:
            raise RuntimeError(
                "Historical cashflow refresh SQL no longer matches the pinned premise"
            )
    if linear:
        # Carry chronology beside its row digest rather than joining the
        # materialized latest-row set back to itself without indexes/statistics.
        # updated_at remains outside the economic digest's JSON field set.
        sql = sql.replace(
            _ROW_FIELDS,
            "                id,\n"
            "                updated_at\n"
            "                FROM selected_cashflows",
        ).replace(_SELF_JOIN, "FROM cashflow_rows")
    return sql.replace(_CREATE, _CREATE.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))


def upgrade() -> None:
    op.execute(sa.text(_refresh_sql(linear=True)))


def downgrade() -> None:
    op.execute(sa.text(_refresh_sql(linear=False)))
