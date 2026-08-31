"""Require attributable tenant ownership on portfolios and ingestion jobs.

Revision ID: c165b2c3d52c
Revises: c163b2c3d52a
Create Date: 2026-08-30

The upgrade normalizes already-attributable tenant values, then aborts before the
schema cutover when any root portfolio remains null, blank, or outside the governed
identifier bound. It never invents or infers a tenant for an ambiguous root record.
Existing ingestion jobs are attributed only from one exact, verified ingestion-write audit
decision carrying the same endpoint, correlation, trace, and bounded request time; the cutover
aborts when that evidence is absent, reused, or conflicting.

The downgrade restores the nullable compatibility shape, but it cannot restore
pre-upgrade whitespace because normalization is intentionally irreversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c165b2c3d52c"
down_revision: str | Sequence[str] | None = "c163b2c3d52a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "portfolios"
_SCOPE_CONSTRAINT = "ck_portfolios_valuation_book_scope_complete"
_TENANT_INDEX = "ix_portfolios_tenant_portfolio_id"
_INGESTION_JOB_TABLE = "ingestion_jobs"
_INGESTION_JOB_TENANT_CHECK = "ck_ingestion_jobs_tenant_authority"
_INGESTION_JOB_TENANT_INDEX = "ix_ingestion_jobs_tenant_submitted_at"
_INGESTION_JOB_IDEMPOTENCY_INDEX = "ix_ingestion_jobs_tenant_endpoint_idempotency_submitted"
_TENANT_TRIM_CHARS = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)
_TENANT_PREFLIGHT = sa.text(
    f"""
    DO $$
    DECLARE
        ambiguous_count bigint;
        portfolio_samples text;
    BEGIN
        PERFORM set_config('lock_timeout', '5s', true);
        LOCK TABLE portfolios IN ACCESS EXCLUSIVE MODE;

        SELECT count(*)
        INTO ambiguous_count
        FROM portfolios
        WHERE tenant_id IS NULL
           OR btrim(tenant_id, {_TENANT_TRIM_CHARS}) = ''
           OR char_length(btrim(tenant_id, {_TENANT_TRIM_CHARS})) > 128;

        SELECT string_agg(portfolio_id, ', ' ORDER BY portfolio_id)
        INTO portfolio_samples
        FROM (
            SELECT portfolio_id
            FROM portfolios
            WHERE tenant_id IS NULL
               OR btrim(tenant_id, {_TENANT_TRIM_CHARS}) = ''
               OR char_length(btrim(tenant_id, {_TENANT_TRIM_CHARS})) > 128
            ORDER BY portfolio_id
            LIMIT 20
        ) AS ambiguous_portfolios;

        IF ambiguous_count > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = format(
                    'portfolio tenant cutover found %s ambiguous root row(s); sample: %s',
                    ambiguous_count,
                    coalesce(portfolio_samples, '<none>')
                ),
                HINT = (
                    'repair each portfolio from authoritative source ownership evidence; '
                    'do not assign a synthetic or deployment-default tenant'
                );
        END IF;

        UPDATE portfolios
        SET tenant_id = btrim(tenant_id, {_TENANT_TRIM_CHARS})
        WHERE tenant_id IS DISTINCT FROM btrim(tenant_id, {_TENANT_TRIM_CHARS});
    END
    $$
    """
)
_DOWNGRADE_PREFLIGHT = sa.text(
    """
    DO $$
    DECLARE
        incompatible_count bigint;
        portfolio_samples text;
    BEGIN
        SELECT count(*)
        INTO incompatible_count
        FROM portfolios
        WHERE tenant_id IS NOT NULL
          AND legal_book_id IS NULL;

        SELECT string_agg(portfolio_id, ', ' ORDER BY portfolio_id)
        INTO portfolio_samples
        FROM (
            SELECT portfolio_id
            FROM portfolios
            WHERE tenant_id IS NOT NULL
              AND legal_book_id IS NULL
            ORDER BY portfolio_id
            LIMIT 20
        ) AS incompatible_portfolios;

        IF incompatible_count > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = format(
                    'portfolio tenant downgrade found %s row(s) without legal-book scope; '
                    'sample: %s',
                    incompatible_count,
                    coalesce(portfolio_samples, '<none>')
                ),
                HINT = (
                    'assign each legal book from authoritative booking evidence before downgrade; '
                    'the rollback will not fabricate accounting scope'
                );
        END IF;
    END
    $$
    """
)
_INGESTION_JOB_TENANT_PREFLIGHT = sa.text(
    f"""
    DO $$
    DECLARE
        ambiguous_count bigint;
        job_samples text;
    BEGIN
        WITH attributable_jobs AS (
            SELECT job.id AS job_row_id, min(audit.tenant_id) AS tenant_id
            FROM ingestion_jobs AS job
            JOIN enterprise_security_audit_events AS audit
              ON audit.component = 'ingestion_service'
             AND audit.route_template = job.endpoint
             AND audit.method = 'POST'
             AND audit.decision = 'ALLOW'
             AND audit.reason = 'authorized'
             AND audit.identity_posture = 'verified'
             AND audit.correlation_id = job.correlation_id
             AND audit.trace_id = job.trace_id
             AND audit.occurred_at <= job.submitted_at
             AND audit.occurred_at >= job.submitted_at - INTERVAL '5 minutes'
            WHERE job.tenant_id IS NULL
              AND audit.tenant_id IS NOT NULL
              AND audit.tenant_id = btrim(audit.tenant_id, {_TENANT_TRIM_CHARS})
              AND audit.tenant_id <> ''
              AND char_length(audit.tenant_id) <= 128
            GROUP BY job.id
            HAVING count(*) = 1
        )
        UPDATE ingestion_jobs AS job
        SET tenant_id = authority.tenant_id
        FROM attributable_jobs AS authority
        WHERE job.tenant_id IS NULL
          AND job.id = authority.job_row_id;

        SELECT count(*)
        INTO ambiguous_count
        FROM ingestion_jobs
        WHERE tenant_id IS NULL;

        SELECT string_agg(job_id, ', ' ORDER BY job_id)
        INTO job_samples
        FROM (
            SELECT job_id
            FROM ingestion_jobs
            WHERE tenant_id IS NULL
            ORDER BY job_id
            LIMIT 20
        ) AS ambiguous_jobs;

        IF ambiguous_count > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = format(
                    'ingestion job tenant cutover found %s unattributable row(s); sample: %s',
                    ambiguous_count,
                    coalesce(job_samples, '<none>')
                ),
                HINT = (
                    'repair each job from authenticated request evidence before cutover; '
                    'do not assign a synthetic or deployment-default tenant'
                );
        END IF;
    END
    $$
    """
)


def upgrade() -> None:
    """Normalize attributable values and fail closed before enforcing ownership."""

    op.execute(_TENANT_PREFLIGHT)
    op.drop_constraint(_SCOPE_CONSTRAINT, _TABLE, type_="check")
    op.alter_column(
        _TABLE,
        "tenant_id",
        existing_type=sa.String(),
        type_=sa.String(length=128),
        nullable=False,
    )
    op.create_check_constraint(
        _SCOPE_CONSTRAINT,
        _TABLE,
        f"tenant_id = btrim(tenant_id, {_TENANT_TRIM_CHARS}) AND tenant_id <> '' AND "
        "(legal_book_id IS NULL OR "
        "(legal_book_id = btrim(legal_book_id) AND legal_book_id <> ''))",
    )
    op.create_index(_TENANT_INDEX, _TABLE, ["tenant_id", "portfolio_id"])
    op.add_column(
        _INGESTION_JOB_TABLE,
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
    )
    op.execute(_INGESTION_JOB_TENANT_PREFLIGHT)
    op.alter_column(
        _INGESTION_JOB_TABLE,
        "tenant_id",
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.create_check_constraint(
        _INGESTION_JOB_TENANT_CHECK,
        _INGESTION_JOB_TABLE,
        f"tenant_id = btrim(tenant_id, {_TENANT_TRIM_CHARS}) "
        "AND tenant_id <> '' AND char_length(tenant_id) <= 128",
    )
    op.create_index(
        _INGESTION_JOB_TENANT_INDEX,
        _INGESTION_JOB_TABLE,
        ["tenant_id", sa.text("submitted_at DESC")],
    )
    op.create_index(
        _INGESTION_JOB_IDEMPOTENCY_INDEX,
        _INGESTION_JOB_TABLE,
        ["tenant_id", "endpoint", "idempotency_key", sa.text("submitted_at DESC")],
    )


def downgrade() -> None:
    """Restore nullable compatibility without fabricating lost pre-cutover values."""

    op.execute(_DOWNGRADE_PREFLIGHT)
    op.drop_index(_INGESTION_JOB_IDEMPOTENCY_INDEX, table_name=_INGESTION_JOB_TABLE)
    op.drop_index(_INGESTION_JOB_TENANT_INDEX, table_name=_INGESTION_JOB_TABLE)
    op.drop_constraint(
        _INGESTION_JOB_TENANT_CHECK,
        _INGESTION_JOB_TABLE,
        type_="check",
    )
    op.drop_column(_INGESTION_JOB_TABLE, "tenant_id")
    op.drop_index(_TENANT_INDEX, table_name=_TABLE)
    op.drop_constraint(_SCOPE_CONSTRAINT, _TABLE, type_="check")
    op.alter_column(
        _TABLE,
        "tenant_id",
        existing_type=sa.String(length=128),
        type_=sa.String(),
        nullable=True,
    )
    op.create_check_constraint(
        _SCOPE_CONSTRAINT,
        _TABLE,
        "(tenant_id IS NULL AND legal_book_id IS NULL) OR "
        "(tenant_id IS NOT NULL AND legal_book_id IS NOT NULL "
        "AND tenant_id = btrim(tenant_id) AND legal_book_id = btrim(legal_book_id) "
        "AND tenant_id <> '' AND legal_book_id <> '')",
    )
