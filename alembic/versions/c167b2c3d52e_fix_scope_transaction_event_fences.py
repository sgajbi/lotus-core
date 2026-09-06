"""Scope transaction processed-event fences by source-owned tenant.

Revision ID: c167b2c3d52e
Revises: c166b2c3d52d
Create Date: 2026-09-07

The table also stores deliberately global market-data fences. Tenant attribution is
therefore nullable, but the transaction-owned service families are backfilled from
their authoritative portfolio and the cutover aborts if any cannot be attributed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c167b2c3d52e"
down_revision: str | Sequence[str] | None = "c166b2c3d52d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "processed_events"
_TRANSACTION_SERVICES = (
    "persistence-transactions",
    "portfolio-transaction-processing",
    "cashflow-calculator",
)
_SERVICE_SQL = ", ".join(f"'{value}'" for value in _TRANSACTION_SERVICES)
_TENANT_CHECK = "ck_processed_events_tenant_authority"
_OLD_PHYSICAL_UNIQUE = "_event_service_uc"
_OLD_SEMANTIC_UNIQUE = "uq_processed_events_service_semantic_key"
_TENANT_PHYSICAL_UNIQUE = "uq_processed_events_tenant_event_service"
_GLOBAL_PHYSICAL_UNIQUE = "uq_processed_events_global_event_service"
_TENANT_SEMANTIC_UNIQUE = "uq_processed_events_tenant_service_semantic_key"
_GLOBAL_SEMANTIC_UNIQUE = "uq_processed_events_global_service_semantic_key"
_TENANT_AUTHORITY_SQL = (
    f"(service_name NOT IN ({_SERVICE_SQL}) OR tenant_id IS NOT NULL) "
    "AND (tenant_id IS NULL OR (tenant_id = btrim(tenant_id) "
    "AND tenant_id <> '' AND char_length(tenant_id) <= 128))"
)


def upgrade() -> None:
    """Attribute retained transaction fences before changing natural keys."""

    op.add_column(_TABLE, sa.Column("tenant_id", sa.String(length=128), nullable=True))
    op.execute(
        sa.text(
            f"""
            UPDATE processed_events AS processed
            SET tenant_id = portfolio.tenant_id
            FROM portfolios AS portfolio
            WHERE processed.service_name IN ({_SERVICE_SQL})
              AND processed.portfolio_id = portfolio.portfolio_id
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                ambiguous_count bigint;
                event_samples text;
            BEGIN
                SELECT count(*)
                INTO ambiguous_count
                FROM processed_events
                WHERE service_name IN ({_SERVICE_SQL})
                  AND tenant_id IS NULL;

                SELECT string_agg(event_id, ', ' ORDER BY event_id)
                INTO event_samples
                FROM (
                    SELECT event_id
                    FROM processed_events
                    WHERE service_name IN ({_SERVICE_SQL})
                      AND tenant_id IS NULL
                    ORDER BY event_id
                    LIMIT 20
                ) AS ambiguous_events;

                IF ambiguous_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'transaction event-fence tenant cutover found %s '
                            'unattributable row(s); sample: %s',
                            ambiguous_count,
                            coalesce(event_samples, '<none>')
                        ),
                        HINT = (
                            'restore the owning portfolio or repair each fence from '
                            'authoritative source evidence; do not assign a synthetic tenant'
                        );
                END IF;
            END
            $$
            """
        )
    )
    op.create_check_constraint(
        _TENANT_CHECK,
        _TABLE,
        _TENANT_AUTHORITY_SQL,
    )
    op.drop_constraint(_OLD_PHYSICAL_UNIQUE, _TABLE, type_="unique")
    op.drop_index(_OLD_SEMANTIC_UNIQUE, table_name=_TABLE)
    op.create_index(
        _TENANT_PHYSICAL_UNIQUE,
        _TABLE,
        ["tenant_id", "event_id", "service_name"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        _GLOBAL_PHYSICAL_UNIQUE,
        _TABLE,
        ["event_id", "service_name"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        _TENANT_SEMANTIC_UNIQUE,
        _TABLE,
        ["tenant_id", "service_name", "semantic_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL AND semantic_key IS NOT NULL"),
    )
    op.create_index(
        _GLOBAL_SEMANTIC_UNIQUE,
        _TABLE,
        ["service_name", "semantic_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL AND semantic_key IS NOT NULL"),
    )


def downgrade() -> None:
    """Restore the legacy global key only when tenant rows do not collide."""

    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                physical_collision_count bigint;
                semantic_collision_count bigint;
            BEGIN
                SELECT count(*) INTO physical_collision_count
                FROM (
                    SELECT event_id, service_name
                    FROM processed_events
                    GROUP BY event_id, service_name
                    HAVING count(*) > 1
                ) AS collisions;

                SELECT count(*) INTO semantic_collision_count
                FROM (
                    SELECT service_name, semantic_key
                    FROM processed_events
                    WHERE semantic_key IS NOT NULL
                    GROUP BY service_name, semantic_key
                    HAVING count(*) > 1
                ) AS collisions;

                IF physical_collision_count > 0 OR semantic_collision_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'cannot remove tenant-scoped event fences: %s physical and '
                            '%s semantic cross-tenant key collision(s) would become ambiguous',
                            physical_collision_count,
                            semantic_collision_count
                        ),
                        HINT = (
                            'retain this revision or reconcile colliding tenant-owned fences '
                            'from authoritative audit evidence before downgrade'
                        );
                END IF;
            END
            $$
            """
        )
    )

    op.drop_index(_GLOBAL_SEMANTIC_UNIQUE, table_name=_TABLE)
    op.drop_index(_TENANT_SEMANTIC_UNIQUE, table_name=_TABLE)
    op.drop_index(_GLOBAL_PHYSICAL_UNIQUE, table_name=_TABLE)
    op.drop_index(_TENANT_PHYSICAL_UNIQUE, table_name=_TABLE)
    op.create_unique_constraint(_OLD_PHYSICAL_UNIQUE, _TABLE, ["event_id", "service_name"])
    op.create_index(
        _OLD_SEMANTIC_UNIQUE,
        _TABLE,
        ["service_name", "semantic_key"],
        unique=True,
        postgresql_where=sa.text("semantic_key IS NOT NULL"),
    )
    op.drop_constraint(_TENANT_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "tenant_id")
