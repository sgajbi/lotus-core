"""Persist source-owned tenant authority on portfolio aggregation jobs.

Revision ID: c168b2c3d52f
Revises: c167b2c3d52e
Create Date: 2026-09-09

The cutover derives every retained job from the authoritative portfolio root and
refuses orphaned work. The derived-state runtime must be quiesced so a legacy
writer cannot insert an unattributed row between backfill and enforcement.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c168b2c3d52f"
down_revision: str | Sequence[str] | None = "c167b2c3d52e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TABLE = "portfolio_aggregation_jobs"
_PORTFOLIO_TABLE = "portfolios"
_LEGACY_UNIQUE = "_portfolio_date_uc"
_PORTFOLIO_TENANT_UNIQUE = "uq_portfolios_tenant_portfolio_id"
_JOB_TENANT_UNIQUE = "uq_portfolio_aggregation_jobs_tenant_portfolio_date"
_JOB_TENANT_FOREIGN_KEY = "fk_portfolio_aggregation_jobs_tenant_portfolio"
_JOB_TENANT_CHECK = "ck_portfolio_aggregation_jobs_tenant_normalized"
_TENANT_INDEX = "ix_portfolio_aggregation_jobs_tenant_portfolio_status_date"


def upgrade() -> None:
    """Backfill and enforce aggregation-job tenant authority."""

    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute(sa.text("LOCK TABLE portfolio_aggregation_jobs IN ACCESS EXCLUSIVE MODE"))
    op.create_unique_constraint(
        _PORTFOLIO_TENANT_UNIQUE,
        _PORTFOLIO_TABLE,
        ["tenant_id", "portfolio_id"],
    )
    op.add_column(_JOB_TABLE, sa.Column("tenant_id", sa.String(length=128), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE portfolio_aggregation_jobs AS job
            SET tenant_id = portfolio.tenant_id
            FROM portfolios AS portfolio
            WHERE job.portfolio_id = portfolio.portfolio_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                unattributable_count bigint;
                job_samples text;
            BEGIN
                SELECT count(*) INTO unattributable_count
                FROM portfolio_aggregation_jobs
                WHERE tenant_id IS NULL;

                SELECT string_agg(id::text, ', ' ORDER BY id)
                INTO job_samples
                FROM (
                    SELECT id
                    FROM portfolio_aggregation_jobs
                    WHERE tenant_id IS NULL
                    ORDER BY id
                    LIMIT 20
                ) AS unattributable_jobs;

                IF unattributable_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'aggregation-job tenant cutover found %s unattributable row(s); '
                            'sample job ids: %s',
                            unattributable_count,
                            coalesce(job_samples, '<none>')
                        ),
                        HINT = (
                            'restore the authoritative portfolio or remove only work proven '
                            'obsolete; never assign a synthetic tenant'
                        );
                END IF;
            END
            $$
            """
        )
    )
    op.alter_column(_JOB_TABLE, "tenant_id", existing_type=sa.String(length=128), nullable=False)
    op.create_check_constraint(
        _JOB_TENANT_CHECK,
        _JOB_TABLE,
        "tenant_id = btrim(tenant_id, E' \\t\\n\\r\\v\\f') "
        "AND tenant_id <> '' AND char_length(tenant_id) <= 128",
    )
    op.drop_constraint(_LEGACY_UNIQUE, _JOB_TABLE, type_="unique")
    op.create_unique_constraint(
        _JOB_TENANT_UNIQUE,
        _JOB_TABLE,
        ["tenant_id", "portfolio_id", "aggregation_date"],
    )
    op.create_foreign_key(
        _JOB_TENANT_FOREIGN_KEY,
        _JOB_TABLE,
        _PORTFOLIO_TABLE,
        ["tenant_id", "portfolio_id"],
        ["tenant_id", "portfolio_id"],
    )
    op.create_index(
        _TENANT_INDEX,
        _JOB_TABLE,
        ["tenant_id", "portfolio_id", "status", "aggregation_date"],
    )


def downgrade() -> None:
    """Restore the globally unique portfolio-day job identity."""

    op.drop_index(_TENANT_INDEX, table_name=_JOB_TABLE)
    op.drop_constraint(_JOB_TENANT_FOREIGN_KEY, _JOB_TABLE, type_="foreignkey")
    op.drop_constraint(_JOB_TENANT_UNIQUE, _JOB_TABLE, type_="unique")
    op.create_unique_constraint(
        _LEGACY_UNIQUE,
        _JOB_TABLE,
        ["portfolio_id", "aggregation_date"],
    )
    op.drop_constraint(_JOB_TENANT_CHECK, _JOB_TABLE, type_="check")
    op.drop_column(_JOB_TABLE, "tenant_id")
    op.drop_constraint(_PORTFOLIO_TENANT_UNIQUE, _PORTFOLIO_TABLE, type_="unique")
