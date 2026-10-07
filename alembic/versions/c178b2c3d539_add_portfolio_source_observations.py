"""Independent immutable portfolio source facts; no qualifying backfill.

Revision ID: c178b2c3d539
Revises: c177b2c3d538
"""

import sqlalchemy as sa

from alembic import op

revision = "c178b2c3d539"
down_revision = "c177b2c3d538"
branch_labels = None
depends_on = None

_IDENTITY = ("tenant_id", "portfolio_id", "producer_id", "source_record_id")
_FAMILIES = ("cash_availability", "funding_investment")


def _fact_table(family):
    return f"portfolio_{family}_observations"


def _head_table(family):
    return f"portfolio_{family}_observation_heads"


def _fact_columns():
    return [
        sa.Column("observation_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("producer_id", sa.String(128), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("source_revision", sa.BigInteger(), nullable=False),
        sa.Column("source_cut_id", sa.String(128), nullable=False),
        sa.Column("definition_version", sa.String(128), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coverage", sa.String(16), nullable=False),
        sa.Column("coverage_scope", sa.String(128), nullable=False),
        sa.Column("predecessor_id", sa.String(64), nullable=True),
        sa.Column("expected_head_hash", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("receipt_job_id", sa.String(), nullable=False),
        sa.Column("admission_policy_version", sa.String(128), nullable=False),
        sa.Column("qualification", sa.String(16), nullable=False),
    ]


def _fact_constraints(table):
    return [
        sa.UniqueConstraint(*_IDENTITY, "source_revision"),
        sa.UniqueConstraint(*_IDENTITY, "observation_id", "content_hash"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"], ["portfolios.tenant_id", "portfolios.portfolio_id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "receipt_job_id"], ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"]
        ),
        sa.ForeignKeyConstraint(
            [*_IDENTITY, "predecessor_id", "expected_head_hash"],
            [f"{table}.{name}" for name in (*_IDENTITY, "observation_id", "content_hash")],
        ),
        sa.CheckConstraint("source_revision > 0"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from"),
        sa.CheckConstraint("generated_at >= observed_at"),
        sa.CheckConstraint("coverage IN ('complete', 'partial', 'missing')"),
        sa.CheckConstraint("qualification = 'unqualified'"),
        sa.CheckConstraint("observation_id = content_hash"),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'"),
        sa.CheckConstraint(
            "(source_revision = 1 AND predecessor_id IS NULL AND expected_head_hash IS NULL) "
            "OR (source_revision > 1 AND predecessor_id IS NOT NULL "
            "AND expected_head_hash IS NOT NULL)"
        ),
    ]


def upgrade():
    # Migration-local DDL remains stable if application models evolve later.
    op.execute("""
        CREATE FUNCTION reject_portfolio_source_observation_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'portfolio source observations are immutable' USING ERRCODE = '23514';
        END;
        $$
    """)
    op.execute("""
        CREATE FUNCTION guard_empty_portfolio_source_observation_truncate() RETURNS trigger
        LANGUAGE plpgsql VOLATILE AS $$
        DECLARE has_history boolean;
        BEGIN
            -- TRUNCATE already holds ACCESS EXCLUSIVE on every affected table.
            -- A volatile SPI SELECT under READ COMMITTED sees freshly committed
            -- history after any lock wait. A transaction-fixed snapshot cannot
            -- establish emptiness and is deliberately unsupported here.
            IF current_setting('transaction_isolation') <> 'read committed' THEN
                RAISE EXCEPTION 'observation truncate requires read committed'
                    USING ERRCODE = '23514';
            END IF;
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I)',
                           TG_TABLE_SCHEMA, TG_TABLE_NAME) INTO has_history;
            IF has_history THEN
                RAISE EXCEPTION 'nonempty portfolio source observations cannot be truncated'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$
    """)
    for family in _FAMILIES:
        table = _fact_table(family)
        columns = _fact_columns()
        constraints = _fact_constraints(table)
        if family == "cash_availability":
            columns.append(sa.Column("currency", sa.String(3), nullable=False))
            constraints.append(sa.CheckConstraint("currency ~ '^[A-Z]{3}$'"))
            for name in ("settled_amount", "encumbered_amount", "available_amount"):
                columns.append(sa.Column(name, sa.Numeric(), nullable=True))
                constraints.append(
                    sa.CheckConstraint(
                        f"CAST({name} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
                        name=f"ck_cash_observation_{name}_finite",
                    )
                )
        else:
            columns.extend(
                [
                    sa.Column("funded", sa.Boolean(), nullable=True),
                    sa.Column("invested", sa.Boolean(), nullable=True),
                ]
            )
        op.create_table(table, *columns, *constraints)
        op.create_table(
            _head_table(family),
            *(
                sa.Column(
                    name,
                    sa.String(128) if name != "portfolio_id" else sa.String(),
                    primary_key=True,
                )
                for name in _IDENTITY
            ),
            sa.Column("observation_id", sa.String(64), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.ForeignKeyConstraint(
                [*_IDENTITY, "observation_id", "content_hash"],
                [f"{table}.{name}" for name in (*_IDENTITY, "observation_id", "content_hash")],
            ),
        )
        # Identifiers are fixed migration-owned constants, never request input.
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_portfolio_source_observation_mutation()"
        )
        for immutable_table in (table, _head_table(family)):
            op.execute(
                f"CREATE TRIGGER {immutable_table}_no_truncate "
                f"BEFORE TRUNCATE ON {immutable_table} FOR EACH STATEMENT "
                "EXECUTE FUNCTION guard_empty_portfolio_source_observation_truncate()"
            )


def downgrade():
    # Fence ALL admission tables before checking emptiness: transaction atomicity
    # alone would not close the READ COMMITTED check-versus-concurrent-insert race.
    if op.get_bind().scalar(sa.text("SHOW transaction_isolation")) != "read committed":
        raise RuntimeError("observation downgrade requires read committed")
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    tables = sorted(
        table for family in _FAMILIES for table in (_fact_table(family), _head_table(family))
    )
    op.execute("LOCK TABLE " + ", ".join(tables) + " IN ACCESS EXCLUSIVE MODE")
    for family in _FAMILIES:
        for table in (_fact_table(family), _head_table(family)):
            if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
                raise RuntimeError(
                    "nonempty portfolio source observation history cannot be downgraded"
                )
    for family in reversed(_FAMILIES):
        op.drop_table(_head_table(family))
        op.drop_table(_fact_table(family))
    op.execute("DROP FUNCTION reject_portfolio_source_observation_mutation()")
    op.execute("DROP FUNCTION guard_empty_portfolio_source_observation_truncate()")
