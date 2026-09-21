"""Persist selected-history sweeps and exact per-security source observations.

Revision ID: c171b2c3d532
Revises: c170b2c3d531
Create Date: 2026-09-21

The sentinel -1 requires one full sweep after upgrade; existing job and fact
epochs are not inferred or rewritten. The sweep populates tenant-scoped exact
selected-fact observations so a later equal-epoch restatement is distinguishable
from replay. The fact lookup index also prevents unchanged history from being
re-armed at each later as-of boundary. A matching Python-strip-equivalent
position-history index keeps legacy security selection bounded. Old runtimes
ignore the new table and columns.
A concurrent, retry-safe build avoids blocking live position-history writers;
its autocommit boundary precedes the transactional table/column additions.
A separate per-fact valuation state records READY/UNAVAILABLE transitions;
selection alone cannot certify readiness or suppress late failed/recovered
valuation restaging.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c171b2c3d532"
down_revision: str | Sequence[str] | None = "c170b2c3d531"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PYTHON_STRIP_BOUNDARY_SQL = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)
_HISTORY_INDEX = "ix_position_history_portfolio_strip_security_date_id"


def _history_index_state() -> (
    tuple[str, int, bool, bool, bool, bool, tuple[str, ...], int, int] | None
):
    row = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT source.relname, catalog.indnkeyatts, catalog.indisunique, "
                "catalog.indisvalid, catalog.indisready, catalog.indpred IS NULL, "
                "pg_get_indexdef(index_relation.oid, 1, true) AS key_1, "
                "pg_get_indexdef(index_relation.oid, 2, true) AS key_2, "
                "pg_get_indexdef(index_relation.oid, 3, true) AS key_3, "
                "pg_get_indexdef(index_relation.oid, 4, true) AS key_4, "
                "catalog.indoption[2] AS key_3_options, "
                "catalog.indoption[3] AS key_4_options "
                "FROM pg_class AS index_relation "
                "JOIN pg_index AS catalog ON catalog.indexrelid = index_relation.oid "
                "JOIN pg_class AS source ON source.oid = catalog.indrelid "
                "JOIN pg_namespace AS schema ON schema.oid = source.relnamespace "
                "WHERE schema.nspname = current_schema() "
                "AND index_relation.relname = :index_name"
            ),
            {"index_name": _HISTORY_INDEX},
        )
        .one_or_none()
    )
    if row is None:
        return None
    return (
        str(row[0]),
        int(row[1]),
        bool(row[2]),
        bool(row[3]),
        bool(row[4]),
        bool(row[5]),
        tuple(str(key) for key in row[6:10]),
        int(row[10] or 0),
        int(row[11] or 0),
    )


def _create_history_index() -> None:
    context = op.get_context()
    with context.autocommit_block():
        if not context.as_sql:
            state = _history_index_state()
            if state is not None:
                (
                    table_name,
                    key_count,
                    unique,
                    valid,
                    ready,
                    unfiltered,
                    keys,
                    date_options,
                    id_options,
                ) = state
                if table_name != "position_history":
                    raise RuntimeError(f"existing {_HISTORY_INDEX} belongs to another table")
                if not valid or not ready:
                    op.drop_index(
                        _HISTORY_INDEX,
                        table_name="position_history",
                        postgresql_concurrently=True,
                    )
                else:
                    strip_characters = op.get_bind().scalar(
                        sa.text(f"SELECT {_PYTHON_STRIP_BOUNDARY_SQL}")
                    )
                    expected_security_key = f"btrim(security_id::text, '{strip_characters}'::text)"
                    if (
                        key_count == 4
                        and not unique
                        and unfiltered
                        and keys == ("portfolio_id", expected_security_key, "position_date", "id")
                        and date_options & 1
                        and id_options & 1
                    ):
                        return
                    raise RuntimeError(f"existing {_HISTORY_INDEX} has unexpected keys: {keys!r}")
        op.create_index(
            _HISTORY_INDEX,
            "position_history",
            [
                "portfolio_id",
                sa.text(f"btrim(security_id, {_PYTHON_STRIP_BOUNDARY_SQL})"),
                sa.text("position_date DESC"),
                sa.text("id DESC"),
            ],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def _drop_history_index() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            _HISTORY_INDEX,
            table_name="position_history",
            postgresql_concurrently=True,
            if_exists=True,
        )


def upgrade() -> None:
    _create_history_index()
    op.create_table(
        "portfolio_selected_history_observations",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("position_history_id", sa.Integer(), nullable=True),
        sa.Column("selected_business_date", sa.Date(), nullable=True),
        sa.Column("selected_nonzero", sa.Boolean(), nullable=False),
        sa.Column("source_fact", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "portfolio_id",
            "as_of_date",
            "security_id",
            name="pk_portfolio_selected_history_observations",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_portfolio_selected_history_observations_tenant_portfolio",
        ),
        sa.CheckConstraint(
            f"tenant_id = btrim(tenant_id, {_PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND tenant_id <> '' "
            "AND char_length(tenant_id) <= 128 "
            f"AND security_id = btrim(security_id, {_PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND security_id <> ''",
            name="ck_portfolio_selected_history_observations_scope",
        ),
        sa.CheckConstraint(
            "(position_history_id IS NULL AND selected_business_date IS NULL "
            "AND source_fact IS NULL AND NOT selected_nonzero) OR "
            "(position_history_id IS NOT NULL AND selected_business_date IS NOT NULL "
            "AND source_fact IS NOT NULL)",
            name="ck_portfolio_selected_history_observations_fact_complete",
        ),
    )
    op.create_index(
        "ix_portfolio_selected_history_observations_fact",
        "portfolio_selected_history_observations",
        [
            "tenant_id",
            "portfolio_id",
            "security_id",
            "position_history_id",
            "selected_business_date",
        ],
    )
    op.create_table(
        "portfolio_selected_history_valuation_states",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("position_history_id", sa.Integer(), nullable=False),
        sa.Column("selected_business_date", sa.Date(), nullable=False),
        sa.Column("source_fact", sa.Text(), nullable=False),
        sa.Column("valuation_outcome", sa.String(length=16), nullable=False),
        sa.Column("valuation_epoch", sa.Integer(), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "portfolio_id",
            "security_id",
            "position_history_id",
            name="pk_portfolio_selected_history_valuation_states",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_portfolio_selected_history_valuation_states_tenant_portfolio",
        ),
        sa.CheckConstraint(
            f"tenant_id = btrim(tenant_id, {_PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND tenant_id <> '' "
            "AND char_length(tenant_id) <= 128 "
            f"AND security_id = btrim(security_id, {_PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND security_id <> ''",
            name="ck_portfolio_selected_history_valuation_states_scope",
        ),
        sa.CheckConstraint(
            "valuation_outcome IN ('READY', 'UNAVAILABLE')",
            name="ck_portfolio_selected_history_valuation_states_outcome",
        ),
        sa.CheckConstraint(
            "valuation_epoch >= 0",
            name="ck_portfolio_selected_history_valuation_states_epoch",
        ),
    )
    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column(
            "selected_history_sweep_epoch",
            sa.Integer(),
            server_default="-1",
            nullable=False,
        ),
    )
    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column(
            "selected_history_collective_epoch",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_portfolio_aggregation_jobs_selected_history_sweep_epoch",
        "portfolio_aggregation_jobs",
        "selected_history_sweep_epoch >= -1",
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_portfolio_aggregation_jobs_selected_history_collective_epoch",
        "portfolio_aggregation_jobs",
        "selected_history_collective_epoch >= 0",
        postgresql_not_valid=True,
    )


def downgrade() -> None:
    _drop_history_index()
    op.drop_constraint(
        "ck_portfolio_aggregation_jobs_selected_history_collective_epoch",
        "portfolio_aggregation_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_portfolio_aggregation_jobs_selected_history_sweep_epoch",
        "portfolio_aggregation_jobs",
        type_="check",
    )
    op.drop_column("portfolio_aggregation_jobs", "selected_history_collective_epoch")
    op.drop_column("portfolio_aggregation_jobs", "selected_history_sweep_epoch")
    op.drop_table("portfolio_selected_history_valuation_states")
    op.drop_table("portfolio_selected_history_observations")
