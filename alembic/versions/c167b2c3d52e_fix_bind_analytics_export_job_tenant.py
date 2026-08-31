"""Bind durable analytics export jobs to authoritative tenant ownership.

Revision ID: c167b2c3d52e
Revises: c166b2c3d52d
Create Date: 2026-08-31

Existing jobs are attributed only through their portfolio. The upgrade aborts when
any job cannot be mapped to one governed portfolio tenant; it never invents a
deployment-default tenant.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c167b2c3d52e"
down_revision: str | Sequence[str] | None = "c166b2c3d52d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "analytics_export_jobs"
_TENANT_CHECK = "ck_analytics_export_jobs_tenant_authority"
_TENANT_PORTFOLIO_FK = "fk_analytics_export_jobs_tenant_portfolio"
_LEGACY_PORTFOLIO_STATUS_INDEX = "ix_analytics_export_jobs_portfolio_status_created_at"
_TENANT_PORTFOLIO_STATUS_INDEX = "ix_analytics_export_jobs_tenant_portfolio_status_created_at"
_LEGACY_FINGERPRINT_INDEX = "ix_analytics_export_jobs_dataset_fingerprint_id"
_TENANT_FINGERPRINT_INDEX = "ix_analytics_export_jobs_tenant_dataset_fingerprint_id"
_TENANT_TRIM_CHARS = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)
_TENANT_BACKFILL = sa.text(
    f"""
    UPDATE analytics_export_jobs AS job
    SET tenant_id = portfolio.tenant_id
    FROM portfolios AS portfolio
    WHERE job.portfolio_id = portfolio.portfolio_id
      AND job.tenant_id IS NULL;

    DO $$
    DECLARE
        ambiguous_count bigint;
        job_samples text;
    BEGIN
        SELECT count(*)
        INTO ambiguous_count
        FROM analytics_export_jobs
        WHERE tenant_id IS NULL
           OR tenant_id <> btrim(tenant_id, {_TENANT_TRIM_CHARS})
           OR tenant_id = ''
           OR char_length(tenant_id) > 128;

        SELECT string_agg(job_id, ', ' ORDER BY job_id)
        INTO job_samples
        FROM (
            SELECT job_id
            FROM analytics_export_jobs
            WHERE tenant_id IS NULL
               OR tenant_id <> btrim(tenant_id, {_TENANT_TRIM_CHARS})
               OR tenant_id = ''
               OR char_length(tenant_id) > 128
            ORDER BY job_id
            LIMIT 20
        ) AS ambiguous_jobs;

        IF ambiguous_count > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = format(
                    'analytics export tenant cutover found %s ambiguous row(s); sample: %s',
                    ambiguous_count,
                    coalesce(job_samples, '<none>')
                ),
                HINT = (
                    'repair portfolio ownership from authoritative evidence before retrying; '
                    'do not assign a synthetic or deployment-default tenant'
                );
        END IF;
    END
    $$
    """
)


def upgrade() -> None:
    """Backfill attributable ownership, then enforce tenant-bound export identity."""

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
    op.drop_index(_LEGACY_PORTFOLIO_STATUS_INDEX, table_name=_TABLE)
    op.create_index(
        _TENANT_PORTFOLIO_STATUS_INDEX,
        _TABLE,
        ["tenant_id", "portfolio_id", "status", "created_at"],
    )
    op.drop_index(_LEGACY_FINGERPRINT_INDEX, table_name=_TABLE)
    op.create_index(
        _TENANT_FINGERPRINT_INDEX,
        _TABLE,
        ["tenant_id", "dataset_type", "request_fingerprint", sa.text("id DESC")],
    )


def downgrade() -> None:
    """Remove export tenant denormalization without changing portfolio ownership."""

    op.drop_index(_TENANT_FINGERPRINT_INDEX, table_name=_TABLE)
    op.create_index(
        _LEGACY_FINGERPRINT_INDEX,
        _TABLE,
        ["dataset_type", "request_fingerprint", sa.text("id DESC")],
    )
    op.drop_index(_TENANT_PORTFOLIO_STATUS_INDEX, table_name=_TABLE)
    op.create_index(
        _LEGACY_PORTFOLIO_STATUS_INDEX,
        _TABLE,
        ["portfolio_id", "status", "created_at"],
    )
    op.drop_constraint(_TENANT_PORTFOLIO_FK, _TABLE, type_="foreignkey")
    op.drop_constraint(_TENANT_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "tenant_id")
