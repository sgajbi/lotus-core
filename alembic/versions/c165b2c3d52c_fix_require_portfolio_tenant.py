"""Require attributable tenant ownership on every portfolio.

Revision ID: c165b2c3d52c
Revises: c163b2c3d52a
Create Date: 2026-08-30

The upgrade normalizes already-attributable tenant values, then aborts before the
schema cutover when any root portfolio remains null, blank, or outside the governed
identifier bound. It never invents or infers a tenant for an ambiguous root record.

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
_TENANT_PREFLIGHT = sa.text(
    """
    DO $$
    DECLARE
        ambiguous_count bigint;
        portfolio_samples text;
    BEGIN
        PERFORM set_config('lock_timeout', '5s', true);
        LOCK TABLE portfolios IN ACCESS EXCLUSIVE MODE;

        UPDATE portfolios
        SET tenant_id = btrim(tenant_id)
        WHERE tenant_id IS NOT NULL
          AND tenant_id IS DISTINCT FROM btrim(tenant_id);

        SELECT count(*)
        INTO ambiguous_count
        FROM portfolios
        WHERE tenant_id IS NULL
           OR tenant_id = ''
           OR char_length(tenant_id) > 128;

        SELECT string_agg(portfolio_id, ', ' ORDER BY portfolio_id)
        INTO portfolio_samples
        FROM (
            SELECT portfolio_id
            FROM portfolios
            WHERE tenant_id IS NULL
               OR tenant_id = ''
               OR char_length(tenant_id) > 128
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
        "tenant_id = btrim(tenant_id) AND tenant_id <> '' AND "
        "(legal_book_id IS NULL OR "
        "(legal_book_id = btrim(legal_book_id) AND legal_book_id <> ''))",
    )
    op.create_index(_TENANT_INDEX, _TABLE, ["tenant_id", "portfolio_id"])


def downgrade() -> None:
    """Restore nullable compatibility without fabricating lost pre-cutover values."""

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
