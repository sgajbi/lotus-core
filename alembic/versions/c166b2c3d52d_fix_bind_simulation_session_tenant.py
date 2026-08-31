"""Bind durable simulation sessions to authoritative tenant ownership.

Revision ID: c166b2c3d52d
Revises: c165b2c3d52c
Create Date: 2026-08-31

Existing sessions are attributed only through their foreign-key-bound portfolio. The
upgrade aborts if any session cannot be mapped to one governed portfolio tenant; it
does not invent a default tenant.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c166b2c3d52d"
down_revision: str | Sequence[str] | None = "c165b2c3d52c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "simulation_sessions"
_TENANT_CHECK = "ck_simulation_sessions_tenant_authority"
_TENANT_INDEX = "ix_simulation_sessions_tenant_id"
_TENANT_SESSION_INDEX = "ix_simulation_sessions_tenant_session_id"
_PORTFOLIO_TENANT_INDEX = "ix_portfolios_tenant_portfolio_id"
_PORTFOLIO_TENANT_UNIQUE = "uq_portfolios_tenant_portfolio_id"
_LEGACY_SESSION_PORTFOLIO_FK = "simulation_sessions_portfolio_id_fkey"
_SESSION_PORTFOLIO_FK = "fk_simulation_sessions_tenant_portfolio"
_TENANT_TRIM_CHARS = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)
_TENANT_BACKFILL = sa.text(
    f"""
    UPDATE simulation_sessions AS session
    SET tenant_id = portfolio.tenant_id
    FROM portfolios AS portfolio
    WHERE session.portfolio_id = portfolio.portfolio_id
      AND session.tenant_id IS NULL;

    DO $$
    DECLARE
        ambiguous_count bigint;
        session_samples text;
    BEGIN
        SELECT count(*)
        INTO ambiguous_count
        FROM simulation_sessions
        WHERE tenant_id IS NULL
           OR tenant_id <> btrim(tenant_id, {_TENANT_TRIM_CHARS})
           OR tenant_id = ''
           OR char_length(tenant_id) > 128;

        SELECT string_agg(session_id, ', ' ORDER BY session_id)
        INTO session_samples
        FROM (
            SELECT session_id
            FROM simulation_sessions
            WHERE tenant_id IS NULL
               OR tenant_id <> btrim(tenant_id, {_TENANT_TRIM_CHARS})
               OR tenant_id = ''
               OR char_length(tenant_id) > 128
            ORDER BY session_id
            LIMIT 20
        ) AS ambiguous_sessions;

        IF ambiguous_count > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = format(
                    'simulation session tenant cutover found %s ambiguous row(s); sample: %s',
                    ambiguous_count,
                    coalesce(session_samples, '<none>')
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
    """Backfill attributable ownership, then enforce tenant-bound session identity."""

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
    op.drop_index(
        _PORTFOLIO_TENANT_INDEX,
        table_name="portfolios",
        if_exists=True,
    )
    op.create_unique_constraint(
        _PORTFOLIO_TENANT_UNIQUE,
        "portfolios",
        ["tenant_id", "portfolio_id"],
    )
    op.drop_constraint(_LEGACY_SESSION_PORTFOLIO_FK, _TABLE, type_="foreignkey")
    op.create_foreign_key(
        _SESSION_PORTFOLIO_FK,
        _TABLE,
        "portfolios",
        ["tenant_id", "portfolio_id"],
        ["tenant_id", "portfolio_id"],
    )
    op.create_index(_TENANT_INDEX, _TABLE, ["tenant_id"])
    op.create_index(_TENANT_SESSION_INDEX, _TABLE, ["tenant_id", "session_id"])


def downgrade() -> None:
    """Remove session tenant denormalization without changing portfolio ownership."""

    op.drop_index(_TENANT_SESSION_INDEX, table_name=_TABLE)
    op.drop_index(_TENANT_INDEX, table_name=_TABLE)
    op.drop_constraint(_SESSION_PORTFOLIO_FK, _TABLE, type_="foreignkey")
    op.create_foreign_key(
        _LEGACY_SESSION_PORTFOLIO_FK,
        _TABLE,
        "portfolios",
        ["portfolio_id"],
        ["portfolio_id"],
    )
    op.drop_constraint(_PORTFOLIO_TENANT_UNIQUE, "portfolios", type_="unique")
    op.create_index(
        _PORTFOLIO_TENANT_INDEX,
        "portfolios",
        ["tenant_id", "portfolio_id"],
    )
    op.drop_constraint(_TENANT_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "tenant_id")
