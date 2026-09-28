"""Scope financial reconciliation persistence to admitted tenant authority.

Revision ID: c174b2c3d535
Revises: c173b2c3d534
Create Date: 2026-09-28

Portfolio-specific history is attributed only from the authoritative portfolio
root. Historical portfolio-wide runs remain explicit estate records; the
cutover never guesses a tenant from incidental findings. Reconciliation writers
must be quiesced while the exclusive migration lock is held.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c174b2c3d535"
down_revision: str | Sequence[str] | None = "c173b2c3d534"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUNS = "financial_reconciliation_runs"
_FINDINGS = "financial_reconciliation_findings"
_PROCESSED_EVENTS = "processed_events"
_PROCESSED_EVENT_TENANT_CHECK = "ck_processed_events_tenant_authority"
_TENANT_TRIM_CHARS = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)

_OLD_RUN_INDEXES: tuple[tuple[str, list[object]], ...] = (
    (
        "ix_fin_recon_scope_revision_type",
        ["portfolio_id", "business_date", "epoch", "aggregation_revision", "reconciliation_type"],
    ),
    (
        "ix_financial_reconciliation_runs_type_status_started_at",
        ["reconciliation_type", "status", sa.text("started_at DESC")],
    ),
    (
        "ix_financial_reconciliation_runs_port_status_started_id",
        ["portfolio_id", "status", sa.text("started_at DESC"), sa.text("id ASC")],
    ),
    (
        "ix_financial_reconciliation_runs_port_type_started_id",
        ["portfolio_id", "reconciliation_type", sa.text("started_at DESC"), sa.text("id DESC")],
    ),
    (
        "ix_fin_recon_runs_port_corr_started_id",
        ["portfolio_id", "correlation_id", sa.text("started_at DESC"), sa.text("id ASC")],
    ),
    (
        "ix_fin_recon_runs_port_req_by_started_id",
        ["portfolio_id", "requested_by", sa.text("started_at DESC"), sa.text("id ASC")],
    ),
    (
        "ix_fin_recon_runs_port_date_epoch_started_id",
        [
            "portfolio_id",
            "business_date",
            "epoch",
            sa.text("started_at DESC"),
            sa.text("id DESC"),
        ],
    ),
)
_NEW_RUN_INDEXES: tuple[tuple[str, list[object]], ...] = (
    (
        "ix_fin_recon_scope_revision_type",
        [
            "tenant_id",
            "portfolio_id",
            "business_date",
            "epoch",
            "aggregation_revision",
            "reconciliation_type",
        ],
    ),
    (
        "ix_fin_recon_runs_tenant_type_status_started",
        ["tenant_id", "reconciliation_type", "status", sa.text("started_at DESC")],
    ),
    (
        "ix_fin_recon_runs_tenant_port_status_started",
        ["tenant_id", "portfolio_id", "status", sa.text("started_at DESC"), sa.text("id ASC")],
    ),
    (
        "ix_fin_recon_runs_tenant_port_type_started",
        [
            "tenant_id",
            "portfolio_id",
            "reconciliation_type",
            sa.text("started_at DESC"),
            sa.text("id DESC"),
        ],
    ),
    (
        "ix_fin_recon_runs_tenant_port_corr_started",
        [
            "tenant_id",
            "portfolio_id",
            "correlation_id",
            sa.text("started_at DESC"),
            sa.text("id ASC"),
        ],
    ),
    (
        "ix_fin_recon_runs_tenant_port_requester_started",
        [
            "tenant_id",
            "portfolio_id",
            "requested_by",
            sa.text("started_at DESC"),
            sa.text("id ASC"),
        ],
    ),
    (
        "ix_fin_recon_runs_tenant_port_date_epoch_started",
        [
            "tenant_id",
            "portfolio_id",
            "business_date",
            "epoch",
            sa.text("started_at DESC"),
            sa.text("id DESC"),
        ],
    ),
)
_OLD_FINDING_INDEXES: tuple[tuple[str, list[object]], ...] = (
    (
        "ix_financial_reconciliation_findings_run_severity_type_id",
        ["run_id", "severity", "finding_type", sa.text("id ASC")],
    ),
    (
        "ix_financial_reconciliation_findings_run_severity_created_id",
        ["run_id", "severity", sa.text("created_at DESC"), sa.text("id DESC")],
    ),
    (
        "ix_fin_recon_findings_run_resolution_severity_created_id",
        [
            "run_id",
            "resolution_state",
            "severity",
            sa.text("created_at ASC"),
            sa.text("id ASC"),
        ],
    ),
)
_NEW_FINDING_INDEXES: tuple[tuple[str, list[object]], ...] = (
    (
        "ix_fin_recon_findings_tenant_run_severity_type",
        ["tenant_id", "run_id", "severity", "finding_type", sa.text("id ASC")],
    ),
    (
        "ix_fin_recon_findings_tenant_run_severity_created",
        ["tenant_id", "run_id", "severity", sa.text("created_at DESC"), sa.text("id DESC")],
    ),
    (
        "ix_fin_recon_findings_tenant_run_resolution_created",
        [
            "tenant_id",
            "run_id",
            "resolution_state",
            "severity",
            sa.text("created_at ASC"),
            sa.text("id ASC"),
        ],
    ),
)


def _drop_indexes(table: str, indexes: tuple[tuple[str, list[object]], ...]) -> None:
    for name, _columns in indexes:
        op.drop_index(name, table_name=table)


def _create_indexes(table: str, indexes: tuple[tuple[str, list[object]], ...]) -> None:
    for name, columns in indexes:
        op.create_index(name, table, columns)


def upgrade() -> None:
    """Backfill explicit authority and install tenant-leading persistence fences."""

    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute(
        sa.text(
            "LOCK TABLE financial_reconciliation_runs, financial_reconciliation_findings, "
            "processed_events, portfolios IN ACCESS EXCLUSIVE MODE"
        )
    )
    op.add_column(_RUNS, sa.Column("authority_scope", sa.String(length=16), nullable=True))
    op.add_column(_RUNS, sa.Column("tenant_id", sa.String(length=128), nullable=True))
    op.add_column(_FINDINGS, sa.Column("authority_scope", sa.String(length=16), nullable=True))
    op.add_column(_FINDINGS, sa.Column("tenant_id", sa.String(length=128), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE processed_events AS processed
            SET tenant_id = portfolio.tenant_id
            FROM portfolios AS portfolio
            WHERE processed.service_name = 'financial-reconciliation-requested'
              AND processed.tenant_id IS NULL
              AND processed.portfolio_id = portfolio.portfolio_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                invalid_count bigint;
                invalid_samples text;
            BEGIN
                SELECT count(*) INTO invalid_count
                FROM processed_events AS processed
                LEFT JOIN portfolios AS portfolio
                  ON portfolio.portfolio_id = processed.portfolio_id
                WHERE processed.service_name = 'financial-reconciliation-requested'
                  AND (
                    portfolio.portfolio_id IS NULL
                    OR processed.tenant_id IS DISTINCT FROM portfolio.tenant_id
                  );

                SELECT string_agg(event_id, ', ' ORDER BY event_id)
                INTO invalid_samples
                FROM (
                    SELECT processed.event_id
                    FROM processed_events AS processed
                    LEFT JOIN portfolios AS portfolio
                      ON portfolio.portfolio_id = processed.portfolio_id
                    WHERE processed.service_name = 'financial-reconciliation-requested'
                      AND (
                        portfolio.portfolio_id IS NULL
                        OR processed.tenant_id IS DISTINCT FROM portfolio.tenant_id
                      )
                    ORDER BY processed.event_id
                    LIMIT 20
                ) AS invalid_events;

                IF invalid_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'reconciliation event-fence tenant cutover found %s '
                            'unattributable row(s); sample: %s',
                            invalid_count,
                            coalesce(invalid_samples, '<none>')
                        ),
                        HINT = (
                            'restore the authoritative portfolio root or repair the fence '
                            'from durable source evidence; never invent a tenant'
                        );
                END IF;
            END
            $$
            """
        )
    )
    op.drop_constraint(
        _PROCESSED_EVENT_TENANT_CHECK,
        _PROCESSED_EVENTS,
        type_="check",
    )
    op.create_check_constraint(
        _PROCESSED_EVENT_TENANT_CHECK,
        _PROCESSED_EVENTS,
        "(service_name NOT IN ('persistence-transactions', "
        "'portfolio-transaction-processing', 'cashflow-calculator', "
        "'financial-reconciliation-requested') OR tenant_id IS NOT NULL) "
        "AND (tenant_id IS NULL OR (tenant_id = btrim(tenant_id) "
        "AND tenant_id <> '' AND char_length(tenant_id) <= 128))",
        postgresql_not_valid=True,
    )
    op.execute(
        sa.text(
            'ALTER TABLE "processed_events" '
            'VALIDATE CONSTRAINT "ck_processed_events_tenant_authority"'
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE financial_reconciliation_runs AS run
            SET authority_scope = 'TENANT', tenant_id = portfolio.tenant_id
            FROM portfolios AS portfolio
            WHERE run.portfolio_id = portfolio.portfolio_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE financial_reconciliation_runs
            SET authority_scope = 'ESTATE', tenant_id = NULL
            WHERE portfolio_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                invalid_count bigint;
                invalid_samples text;
            BEGIN
                SELECT count(*) INTO invalid_count
                FROM financial_reconciliation_runs
                WHERE authority_scope IS NULL
                   OR (authority_scope = 'TENANT' AND (
                        tenant_id IS NULL
                        OR tenant_id <> btrim(tenant_id, {_TENANT_TRIM_CHARS})
                        OR tenant_id = ''
                        OR char_length(tenant_id) > 128
                   ))
                   OR (authority_scope = 'ESTATE' AND (
                        tenant_id IS NOT NULL OR portfolio_id IS NOT NULL
                   ));

                SELECT string_agg(run_id, ', ' ORDER BY run_id)
                INTO invalid_samples
                FROM (
                    SELECT run_id
                    FROM financial_reconciliation_runs
                    WHERE authority_scope IS NULL
                       OR (authority_scope = 'TENANT' AND (
                            tenant_id IS NULL
                            OR tenant_id <> btrim(tenant_id, {_TENANT_TRIM_CHARS})
                            OR tenant_id = ''
                            OR char_length(tenant_id) > 128
                       ))
                       OR (authority_scope = 'ESTATE' AND (
                            tenant_id IS NOT NULL OR portfolio_id IS NOT NULL
                       ))
                    ORDER BY run_id
                    LIMIT 20
                ) AS invalid_runs;

                IF invalid_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'reconciliation tenant cutover found %s unattributable run(s); '
                            'sample: %s',
                            invalid_count,
                            coalesce(invalid_samples, '<none>')
                        ),
                        HINT = (
                            'restore the authoritative portfolio root or classify only a '
                            'genuinely portfolio-wide historical run as ESTATE; '
                            'never invent a tenant'
                        );
                END IF;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE financial_reconciliation_findings AS finding
            SET authority_scope = run.authority_scope, tenant_id = run.tenant_id
            FROM financial_reconciliation_runs AS run
            WHERE finding.run_id = run.run_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                invalid_count bigint;
                invalid_samples text;
            BEGIN
                SELECT count(*) INTO invalid_count
                FROM financial_reconciliation_findings AS finding
                LEFT JOIN financial_reconciliation_runs AS run
                  ON run.run_id = finding.run_id
                LEFT JOIN portfolios AS portfolio
                  ON portfolio.portfolio_id = finding.portfolio_id
                WHERE run.run_id IS NULL
                   OR finding.authority_scope IS DISTINCT FROM run.authority_scope
                   OR finding.tenant_id IS DISTINCT FROM run.tenant_id
                   OR (
                        finding.authority_scope = 'TENANT'
                        AND finding.portfolio_id IS NOT NULL
                        AND (
                            portfolio.portfolio_id IS NULL
                            OR portfolio.tenant_id IS DISTINCT FROM finding.tenant_id
                        )
                   );

                SELECT string_agg(finding_id, ', ' ORDER BY finding_id)
                INTO invalid_samples
                FROM (
                    SELECT finding.finding_id
                    FROM financial_reconciliation_findings AS finding
                    LEFT JOIN financial_reconciliation_runs AS run
                      ON run.run_id = finding.run_id
                    LEFT JOIN portfolios AS portfolio
                      ON portfolio.portfolio_id = finding.portfolio_id
                    WHERE run.run_id IS NULL
                       OR finding.authority_scope IS DISTINCT FROM run.authority_scope
                       OR finding.tenant_id IS DISTINCT FROM run.tenant_id
                       OR (
                            finding.authority_scope = 'TENANT'
                            AND finding.portfolio_id IS NOT NULL
                            AND (
                                portfolio.portfolio_id IS NULL
                                OR portfolio.tenant_id IS DISTINCT FROM finding.tenant_id
                            )
                       )
                    ORDER BY finding.finding_id
                    LIMIT 20
                ) AS invalid_findings;

                IF invalid_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'reconciliation tenant cutover found %s conflicting finding(s); '
                            'sample: %s',
                            invalid_count,
                            coalesce(invalid_samples, '<none>')
                        ),
                        HINT = (
                            'repair each finding from its authoritative run and portfolio; '
                            'never assign a synthetic tenant'
                        );
                END IF;
            END
            $$
            """
        )
    )

    op.alter_column(
        _RUNS,
        "authority_scope",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default="TENANT",
    )
    op.alter_column(
        _FINDINGS,
        "authority_scope",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default="TENANT",
    )
    op.create_check_constraint(
        "ck_fin_recon_runs_authority_scope",
        _RUNS,
        f"(authority_scope = 'TENANT' AND tenant_id IS NOT NULL "
        f"AND tenant_id = btrim(tenant_id, {_TENANT_TRIM_CHARS}) "
        "AND tenant_id <> '' AND char_length(tenant_id) <= 128) "
        "OR (authority_scope = 'ESTATE' AND tenant_id IS NULL AND portfolio_id IS NULL)",
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_fin_recon_findings_authority_scope",
        _FINDINGS,
        f"(authority_scope = 'TENANT' AND tenant_id IS NOT NULL "
        f"AND tenant_id = btrim(tenant_id, {_TENANT_TRIM_CHARS}) "
        "AND tenant_id <> '' AND char_length(tenant_id) <= 128) "
        "OR (authority_scope = 'ESTATE' AND tenant_id IS NULL)",
        postgresql_not_valid=True,
    )
    op.create_unique_constraint(
        "uq_fin_recon_runs_authority_run",
        _RUNS,
        ["authority_scope", "tenant_id", "run_id"],
    )
    op.create_unique_constraint(
        "uq_fin_recon_runs_scope_run",
        _RUNS,
        ["authority_scope", "run_id"],
    )
    op.create_foreign_key(
        "fk_fin_recon_runs_tenant_portfolio",
        _RUNS,
        "portfolios",
        ["tenant_id", "portfolio_id"],
        ["tenant_id", "portfolio_id"],
    )
    op.create_foreign_key(
        "fk_fin_recon_findings_scope_run",
        _FINDINGS,
        _RUNS,
        ["authority_scope", "run_id"],
        ["authority_scope", "run_id"],
    )
    op.create_foreign_key(
        "fk_fin_recon_findings_authority_run",
        _FINDINGS,
        _RUNS,
        ["authority_scope", "tenant_id", "run_id"],
        ["authority_scope", "tenant_id", "run_id"],
    )
    op.create_foreign_key(
        "fk_fin_recon_findings_tenant_portfolio",
        _FINDINGS,
        "portfolios",
        ["tenant_id", "portfolio_id"],
        ["tenant_id", "portfolio_id"],
    )
    op.execute(
        sa.text(
            'ALTER TABLE "financial_reconciliation_runs" '
            'VALIDATE CONSTRAINT "ck_fin_recon_runs_authority_scope"'
        )
    )
    op.execute(
        sa.text(
            'ALTER TABLE "financial_reconciliation_findings" '
            'VALIDATE CONSTRAINT "ck_fin_recon_findings_authority_scope"'
        )
    )

    op.drop_index("ix_financial_reconciliation_runs_dedupe_key", table_name=_RUNS)
    op.create_index(
        "uq_fin_recon_runs_tenant_dedupe",
        _RUNS,
        ["tenant_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("authority_scope = 'TENANT' AND dedupe_key IS NOT NULL"),
    )
    _drop_indexes(_RUNS, _OLD_RUN_INDEXES)
    _create_indexes(_RUNS, _NEW_RUN_INDEXES)
    _drop_indexes(_FINDINGS, _OLD_FINDING_INDEXES)
    _create_indexes(_FINDINGS, _NEW_FINDING_INDEXES)


def downgrade() -> None:
    """Restore global keys only when retained tenant data is representable."""

    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute(
        sa.text(
            "LOCK TABLE financial_reconciliation_runs, financial_reconciliation_findings, "
            "processed_events "
            "IN ACCESS EXCLUSIVE MODE"
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                collision_count bigint;
                collision_samples text;
            BEGIN
                SELECT count(*) INTO collision_count
                FROM (
                    SELECT dedupe_key
                    FROM financial_reconciliation_runs
                    WHERE dedupe_key IS NOT NULL
                    GROUP BY dedupe_key
                    HAVING count(*) > 1
                ) AS collisions;

                SELECT string_agg(dedupe_key, ', ' ORDER BY dedupe_key)
                INTO collision_samples
                FROM (
                    SELECT dedupe_key
                    FROM financial_reconciliation_runs
                    WHERE dedupe_key IS NOT NULL
                    GROUP BY dedupe_key
                    HAVING count(*) > 1
                    ORDER BY dedupe_key
                    LIMIT 20
                ) AS collisions;

                IF collision_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'reconciliation tenant downgrade found %s global dedupe collision(s); '
                            'sample: %s',
                            collision_count,
                            coalesce(collision_samples, '<none>')
                        ),
                        HINT = (
                            'retain the tenant-scoped schema or reconcile the duplicate keys '
                            'from authoritative run history before downgrade'
                        );
                END IF;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                tenant_wide_count bigint;
                tenant_wide_samples text;
            BEGIN
                SELECT count(*) INTO tenant_wide_count
                FROM financial_reconciliation_runs
                WHERE authority_scope = 'TENANT' AND portfolio_id IS NULL;

                SELECT string_agg(run_id, ', ' ORDER BY run_id)
                INTO tenant_wide_samples
                FROM (
                    SELECT run_id
                    FROM financial_reconciliation_runs
                    WHERE authority_scope = 'TENANT' AND portfolio_id IS NULL
                    ORDER BY run_id
                    LIMIT 20
                ) AS tenant_wide_runs;

                IF tenant_wide_count > 0 THEN
                    RAISE EXCEPTION USING
                        MESSAGE = format(
                            'reconciliation tenant downgrade found %s tenant-wide run(s) '
                            'that cannot preserve authority; sample: %s',
                            tenant_wide_count,
                            coalesce(tenant_wide_samples, '<none>')
                        ),
                        HINT = (
                            'retain the tenant-scoped schema or archive the tenant-wide run '
                            'with governed authority evidence before downgrade'
                        );
                END IF;
            END
            $$
            """
        )
    )

    _drop_indexes(_FINDINGS, _NEW_FINDING_INDEXES)
    _create_indexes(_FINDINGS, _OLD_FINDING_INDEXES)
    _drop_indexes(_RUNS, _NEW_RUN_INDEXES)
    _create_indexes(_RUNS, _OLD_RUN_INDEXES)
    op.drop_index("uq_fin_recon_runs_tenant_dedupe", table_name=_RUNS)
    op.create_index(
        "ix_financial_reconciliation_runs_dedupe_key",
        _RUNS,
        ["dedupe_key"],
        unique=True,
    )
    op.drop_constraint(
        "fk_fin_recon_findings_tenant_portfolio",
        _FINDINGS,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_fin_recon_findings_authority_run",
        _FINDINGS,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_fin_recon_findings_scope_run",
        _FINDINGS,
        type_="foreignkey",
    )
    op.drop_constraint("fk_fin_recon_runs_tenant_portfolio", _RUNS, type_="foreignkey")
    op.drop_constraint("uq_fin_recon_runs_scope_run", _RUNS, type_="unique")
    op.drop_constraint("uq_fin_recon_runs_authority_run", _RUNS, type_="unique")
    op.drop_constraint("ck_fin_recon_findings_authority_scope", _FINDINGS, type_="check")
    op.drop_constraint("ck_fin_recon_runs_authority_scope", _RUNS, type_="check")
    op.drop_constraint(
        _PROCESSED_EVENT_TENANT_CHECK,
        _PROCESSED_EVENTS,
        type_="check",
    )
    op.create_check_constraint(
        _PROCESSED_EVENT_TENANT_CHECK,
        _PROCESSED_EVENTS,
        "(service_name NOT IN ('persistence-transactions', "
        "'portfolio-transaction-processing', 'cashflow-calculator') "
        "OR tenant_id IS NOT NULL) AND (tenant_id IS NULL OR "
        "(tenant_id = btrim(tenant_id) AND tenant_id <> '' "
        "AND char_length(tenant_id) <= 128))",
    )
    op.drop_column(_FINDINGS, "tenant_id")
    op.drop_column(_FINDINGS, "authority_scope")
    op.drop_column(_RUNS, "tenant_id")
    op.drop_column(_RUNS, "authority_scope")
