"""Immutable flow source facts and complete manifests, without legacy backfill.

Revision ID: c187b2c3d548
Revises: c186b2c3d547
"""

import sqlalchemy as sa

from alembic import op

revision = "c187b2c3d548"
down_revision = "c186b2c3d547"
branch_labels = None
depends_on = None

FACT = "portfolio_flow_event_observations"
HEAD = "portfolio_flow_event_observation_heads"
CUT = "portfolio_flow_source_cuts"
IDENTITY = ("tenant_id", "portfolio_id", "producer_id", "source_record_id")
CUT_SCOPE = ("tenant_id", "portfolio_id", "source_system", "source_cut_id")


def _fact_columns():
    # Frozen migration-local columns; application model changes cannot rewrite history.
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
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("posting_state", sa.String(16), nullable=False),
        sa.Column("reversal_state", sa.String(16), nullable=False),
        sa.Column("reverses_event_id", sa.String(128), nullable=True),
        sa.Column("reversal_target", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("economic_event_id", sa.String(128), nullable=True),
        sa.Column("transaction_id", sa.String(128), nullable=True),
    ]


def _fact_constraints():
    return [
        sa.UniqueConstraint(*IDENTITY, "source_revision"),
        sa.UniqueConstraint(*IDENTITY, "observation_id", "content_hash"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"], ["portfolios.tenant_id", "portfolios.portfolio_id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "receipt_job_id"], ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"]
        ),
        sa.ForeignKeyConstraint(
            [*IDENTITY, "predecessor_id", "expected_head_hash"],
            [f"{FACT}.{k}" for k in (*IDENTITY, "observation_id", "content_hash")],
        ),
        *(
            sa.CheckConstraint(value)
            for value in (
                "source_revision > 0",
                "effective_to IS NULL OR effective_to > effective_from",
                "generated_at >= observed_at",
                "coverage IN ('complete', 'partial', 'missing')",
                "qualification = 'unqualified'",
                "observation_id = content_hash",
                "content_hash ~ '^[0-9a-f]{64}$'",
                "(source_revision=1 AND predecessor_id IS NULL AND expected_head_hash IS "
                "NULL) OR (source_revision>1 AND predecessor_id IS NOT NULL AND "
                "expected_head_hash IS NOT NULL)",
                "currency ~ '^[A-Z]{3}$'",
                "posting_state IN ('POSTED','CANCELLED','UNKNOWN')",
                "reversal_state IN ('NONE','REVERSES','UNKNOWN')",
                "classification IN ('EXTERNAL_CASH','INTERNAL_TRANSFER','REVERSAL','IN_KIND')",
                "(reversal_state = 'REVERSES') = (reverses_event_id IS NOT NULL)",
                "(reversal_state = 'REVERSES') = (reversal_target IS NOT NULL)",
                "reversal_target IS NULL OR (jsonb_typeof(reversal_target::jsonb)='object' "
                "AND jsonb_typeof(reversal_target::jsonb->'source_record_id')='string' "
                "AND jsonb_typeof(reversal_target::jsonb->'observation_id')='string' "
                "AND jsonb_typeof(reversal_target::jsonb->'content_hash')='string' "
                "AND jsonb_typeof(reversal_target::jsonb->'flow_source_record_revision')='number' "
                "AND reversal_target::jsonb ?& "
                "ARRAY['source_record_id','observation_id','content_hash',"
                "'flow_source_record_revision'] "
                "AND reversal_target::jsonb - 'source_record_id' - 'observation_id' - "
                "'content_hash' - 'flow_source_record_revision' = '{}'::jsonb "
                "AND reversal_target::jsonb->>'source_record_id' = reverses_event_id "
                "AND reversal_target::jsonb->>'observation_id' ~ '^[0-9a-f]{64}$' "
                "AND reversal_target::jsonb->>'content_hash' = "
                "reversal_target::jsonb->>'observation_id' "
                "AND reversal_target::jsonb->>'flow_source_record_revision' ~ '^[1-9][0-9]*$')",
                "(classification = 'REVERSAL') = (reversal_state = 'REVERSES')",
                "reverses_event_id IS NULL OR reverses_event_id <> source_record_id",
                "business_date >= effective_from AND (effective_to IS NULL OR business_date "
                "< effective_to)",
                "isfinite(received_at) AND isfinite(observed_at) AND isfinite(generated_at)",
            )
        ),
        sa.CheckConstraint(
            "CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_flow_observation_amount_finite",
        ),
    ]


def _create_cut():
    op.create_table(
        CUT,
        sa.Column("manifest_hash", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("source_system", sa.String(128), nullable=False),
        sa.Column("source_cut_id", sa.String(128), nullable=False),
        sa.Column("cut_revision", sa.BigInteger(), nullable=False),
        sa.Column("definition_version", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("coverage_from", sa.Date(), nullable=False),
        sa.Column("coverage_to", sa.Date(), nullable=False),
        sa.Column("coverage", sa.String(16), nullable=False),
        sa.Column("event_pins", sa.JSON(), nullable=False),
        sa.Column("dependency_pins", sa.JSON(), nullable=False),
        sa.Column("predecessor_cut_hash", sa.String(64), nullable=True),
        sa.Column("expected_head_hash", sa.String(64), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_job_id", sa.String(), nullable=False),
        sa.UniqueConstraint(*CUT_SCOPE, "cut_revision"),
        sa.UniqueConstraint(*CUT_SCOPE, "manifest_hash"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"], ["portfolios.tenant_id", "portfolios.portfolio_id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "receipt_job_id"], ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"]
        ),
        sa.ForeignKeyConstraint(
            [*CUT_SCOPE, "predecessor_cut_hash"],
            [f"{CUT}.{k}" for k in (*CUT_SCOPE, "manifest_hash")],
        ),
        *(
            sa.CheckConstraint(value)
            for value in (
                "cut_revision > 0 AND coverage_to >= coverage_from",
                "manifest_hash ~ '^[0-9a-f]{64}$' AND currency ~ '^[A-Z]{3}$'",
                "coverage IN ('complete','partial','missing') AND "
                "jsonb_typeof(event_pins::jsonb)='array'",
                "jsonb_array_length(event_pins::jsonb) <= 1000",
                "jsonb_typeof(dependency_pins::jsonb)='array' AND "
                "jsonb_array_length(event_pins::jsonb) + "
                "jsonb_array_length(dependency_pins::jsonb) <= 1000",
                "isfinite(received_at)",
                "(cut_revision=1 AND predecessor_cut_hash IS NULL AND expected_head_hash IS "
                "NULL) OR (cut_revision>1 AND predecessor_cut_hash=expected_head_hash AND "
                "predecessor_cut_hash IS NOT NULL)",
            )
        ),
    )
    op.create_index(
        "uq_flow_cut_successor",
        CUT,
        ["predecessor_cut_hash"],
        unique=True,
        postgresql_where=sa.text("predecessor_cut_hash IS NOT NULL"),
    )


def upgrade():
    op.create_table(FACT, *_fact_columns(), *_fact_constraints())
    op.create_index(
        "ix_flow_source_window_membership",
        FACT,
        [
            "tenant_id",
            "portfolio_id",
            "producer_id",
            "currency",
            "definition_version",
            "business_date",
            "source_record_id",
        ],
    )
    op.create_index(
        "uq_flow_event_successor",
        FACT,
        ["predecessor_id"],
        unique=True,
        postgresql_where=sa.text("predecessor_id IS NOT NULL"),
    )
    op.create_table(
        HEAD,
        *(
            sa.Column(k, sa.String() if k == "portfolio_id" else sa.String(128), primary_key=True)
            for k in IDENTITY
        ),
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            [*IDENTITY, "observation_id", "content_hash"],
            [f"{FACT}.{k}" for k in (*IDENTITY, "observation_id", "content_hash")],
        ),
    )
    _create_cut()
    # Stable c178 functions reject UPDATE/DELETE and nonempty TRUNCATE history.
    for table in (FACT, CUT):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR "
            f"EACH ROW EXECUTE FUNCTION reject_portfolio_source_observation_mutation()"
        )
    for table in (FACT, HEAD, CUT):
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH "
            f"STATEMENT EXECUTE FUNCTION "
            f"guard_empty_portfolio_source_observation_truncate()"
        )


def downgrade():
    if op.get_bind().scalar(sa.text("SHOW transaction_isolation")) != "read committed":
        raise RuntimeError("flow observation downgrade requires read committed")
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute("LOCK TABLE " + ", ".join(sorted((FACT, HEAD, CUT))) + " IN ACCESS EXCLUSIVE MODE")
    for table in (FACT, HEAD, CUT):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("nonempty flow source history cannot be downgraded")
    for table in (CUT, HEAD, FACT):
        op.drop_table(table)
