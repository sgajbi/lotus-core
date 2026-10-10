"""Retain exact portfolio-owner authority throughout valuation work.

Revision ID: c185b2c3d546
Revises: c184b2c3d545

Drain valuation staging, scheduling and calculator writers before the cutover.
Historical ambiguity refuses the transaction; no synthetic tenant is assigned.
"""

import sqlalchemy as sa

from alembic import op

revision = "c185b2c3d546"
down_revision = "c184b2c3d545"
branch_labels = None
depends_on = None

_TABLE = "portfolio_valuation_jobs"
_LEGACY_UNIQUE = "_portfolio_security_valuation_date_epoch_uc"
_TENANT_UNIQUE = "uq_portfolio_valuation_jobs_tenant_scope_epoch"
_FOREIGN_KEY = "fk_portfolio_valuation_jobs_tenant_portfolio"
_CHECK = "ck_portfolio_valuation_jobs_tenant_normalized"
_STRIP = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)
_CANONICAL_TENANT = (
    f"tenant_id = btrim(tenant_id, {_STRIP}) AND tenant_id <> '' AND char_length(tenant_id) <= 128"
)


def _lock_sources() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    # Match staging's root-before-job order and fence attribution changes.
    op.execute(sa.text("LOCK TABLE portfolios IN SHARE ROW EXCLUSIVE MODE"))
    op.execute(sa.text("LOCK TABLE portfolio_valuation_jobs IN ACCESS EXCLUSIVE MODE"))


def upgrade() -> None:
    _lock_sources()
    # Inspect exact source identities before adding columns or rewriting any job.
    op.execute(
        sa.text(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM portfolio_valuation_jobs AS job
                WHERE (
                    SELECT count(*) FROM portfolios AS portfolio
                    WHERE portfolio.portfolio_id = job.portfolio_id
                      AND portfolio.tenant_id IS NOT NULL
                      AND portfolio.tenant_id = btrim(portfolio.tenant_id, {_STRIP})
                      AND portfolio.tenant_id <> ''
                      AND char_length(portfolio.tenant_id) <= 128
                ) <> 1
            ) THEN
                RAISE EXCEPTION 'valuation-job tenant cutover found unprovable ownership'
                    USING HINT = 'restore exact authoritative portfolio evidence; never trim '
                                 'portfolio identities or assign a synthetic tenant';
            END IF;
        END $$
    """)
    )
    op.add_column(_TABLE, sa.Column("tenant_id", sa.String(128), nullable=True))
    op.execute(
        sa.text("""
        UPDATE portfolio_valuation_jobs AS job
        SET tenant_id = portfolio.tenant_id
        FROM portfolios AS portfolio
        WHERE job.portfolio_id = portfolio.portfolio_id
    """)
    )
    op.alter_column(_TABLE, "tenant_id", existing_type=sa.String(128), nullable=False)
    op.create_check_constraint(_CHECK, _TABLE, _CANONICAL_TENANT)
    op.drop_constraint(_LEGACY_UNIQUE, _TABLE, type_="unique")
    op.create_unique_constraint(
        _TENANT_UNIQUE,
        _TABLE,
        ["tenant_id", "portfolio_id", "security_id", "valuation_date", "epoch"],
    )
    op.create_foreign_key(
        _FOREIGN_KEY,
        _TABLE,
        "portfolios",
        ["tenant_id", "portfolio_id"],
        ["tenant_id", "portfolio_id"],
    )


def downgrade() -> None:
    _lock_sources()
    op.execute(
        sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM portfolio_valuation_jobs
                GROUP BY portfolio_id, security_id, valuation_date, epoch
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'valuation-job tenant downgrade would collapse owned work';
            END IF;
        END $$
    """)
    )
    op.drop_constraint(_FOREIGN_KEY, _TABLE, type_="foreignkey")
    op.drop_constraint(_TENANT_UNIQUE, _TABLE, type_="unique")
    op.create_unique_constraint(
        _LEGACY_UNIQUE,
        _TABLE,
        ["portfolio_id", "security_id", "valuation_date", "epoch"],
    )
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "tenant_id")
