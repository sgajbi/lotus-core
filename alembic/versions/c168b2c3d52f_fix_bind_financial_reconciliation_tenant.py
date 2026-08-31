"""Bind financial reconciliation evidence to authoritative tenant ownership.

Revision ID: c168b2c3d52f
Revises: c167b2c3d52e
Create Date: 2026-08-31

Portfolio-scoped legacy runs are attributable through their governed portfolio.
The upgrade aborts when any run remains unattributable, including estate-wide
legacy runs, so operators must repair ownership from authoritative evidence
rather than accepting a synthetic tenant.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c168b2c3d52f"
down_revision: str | Sequence[str] | None = "c167b2c3d52e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "financial_reconciliation_runs"
_TENANT_CHECK = "ck_fin_recon_tenant"
_TENANT_PORTFOLIO_FK = "fk_fin_recon_runs_tenant_portfolio"
_TENANT_STARTED_INDEX = "ix_fin_recon_runs_tenant_started_id"
_TENANT_PORTFOLIO_STARTED_INDEX = "ix_fin_recon_tenant_port"
_TENANT_TRIM_CHARS = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)
_TENANT_BACKFILL = sa.text(
    f"""
    UPDATE financial_reconciliation_runs AS run
    SET tenant_id = portfolio.tenant_id
    FROM portfolios AS portfolio
    WHERE run.portfolio_id = portfolio.portfolio_id
      AND run.tenant_id IS NULL;

    DO $$
    DECLARE
        ambiguous_count bigint;
        run_samples text;
    BEGIN
        SELECT count(*)
        INTO ambiguous_count
        FROM financial_reconciliation_runs
        WHERE tenant_id IS NULL
           OR tenant_id <> btrim(tenant_id, {_TENANT_TRIM_CHARS})
           OR tenant_id = ''
           OR char_length(tenant_id) > 128;

        SELECT string_agg(run_id, ', ' ORDER BY run_id)
        INTO run_samples
        FROM (
            SELECT run_id
            FROM financial_reconciliation_runs
            WHERE tenant_id IS NULL
               OR tenant_id <> btrim(tenant_id, {_TENANT_TRIM_CHARS})
               OR tenant_id = ''
               OR char_length(tenant_id) > 128
            ORDER BY run_id
            LIMIT 20
        ) AS ambiguous_runs;

        IF ambiguous_count > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = format(
                    'financial reconciliation tenant cutover found %s ambiguous row(s); sample: %s',
                    ambiguous_count,
                    coalesce(run_samples, '<none>')
                ),
                HINT = (
                    'repair run ownership from authoritative evidence before retrying; '
                    'do not assign a synthetic or deployment-default tenant'
                );
        END IF;
    END
    $$
    """
)


def upgrade() -> None:
    """Backfill attributable runs, then enforce tenant-bound control evidence."""

    op.add_column(_TABLE, sa.Column("tenant_id", sa.String(length=128), nullable=True))
    op.execute(_TENANT_BACKFILL)
    op.alter_column(
        _TABLE,
        "tenant_id",
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.create_check_constraint(
        _TENANT_CHECK,
        _TABLE,
        f"tenant_id = btrim(tenant_id, {_TENANT_TRIM_CHARS}) AND tenant_id <> ''",
    )
    op.create_foreign_key(
        _TENANT_PORTFOLIO_FK,
        _TABLE,
        "portfolios",
        ["tenant_id", "portfolio_id"],
        ["tenant_id", "portfolio_id"],
    )
    op.create_index(
        _TENANT_STARTED_INDEX,
        _TABLE,
        ["tenant_id", sa.text("started_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        _TENANT_PORTFOLIO_STARTED_INDEX,
        _TABLE,
        ["tenant_id", "portfolio_id", sa.text("started_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    """Remove reconciliation tenant denormalization without changing portfolios."""

    op.drop_index(_TENANT_PORTFOLIO_STARTED_INDEX, table_name=_TABLE)
    op.drop_index(_TENANT_STARTED_INDEX, table_name=_TABLE)
    op.drop_constraint(_TENANT_PORTFOLIO_FK, _TABLE, type_="foreignkey")
    op.drop_constraint(_TENANT_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "tenant_id")
