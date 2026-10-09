"""Append-only fact-verification receipts; original observations stay unchanged.

Revision ID: c181b2c3d542
Revises: c179b2c3d540
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c181b2c3d542"
down_revision = "c179b2c3d540"
branch_labels = None
depends_on = None
TABLE = "portfolio_source_fact_verifications"


def upgrade() -> None:
    identity = ("tenant_id", "portfolio_id", "producer_id", "source_record_id")
    op.create_table(
        TABLE,
        sa.Column("attestation_sha256", sa.String(64), primary_key=True),
        *(sa.Column(name, sa.String(128), nullable=False) for name in identity),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("cash_observation_id", sa.String(64), nullable=True),
        sa.Column("funding_observation_id", sa.String(64), nullable=True),
        sa.Column("consumer_id", sa.String(128), nullable=False),
        sa.Column("receipt", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        *(
            sa.ForeignKeyConstraint(
                [*identity, column, "content_hash"],
                [f"{table}.{name}" for name in (*identity, "observation_id", "content_hash")],
            )
            for column, table in (
                ("cash_observation_id", "portfolio_cash_availability_observations"),
                ("funding_observation_id", "portfolio_funding_investment_observations"),
            )
        ),
        sa.CheckConstraint("(cash_observation_id IS NULL) <> (funding_observation_id IS NULL)"),
        sa.CheckConstraint("coalesce(cash_observation_id, funding_observation_id) = content_hash"),
        sa.CheckConstraint("attestation_sha256 ~ '^[0-9a-f]{64}$'"),
        sa.CheckConstraint("jsonb_typeof(receipt) = 'object' AND isfinite(received_at)"),
    )
    op.create_index(
        "ix_source_fact_verification_custody",
        TABLE,
        ["tenant_id", "portfolio_id", "content_hash", "consumer_id"],
    )
    op.execute("""
        CREATE FUNCTION refuse_source_fact_verification_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'SOURCE_FACT_VERIFICATION_IMMUTABLE';
        END $$
    """)
    for event, level in (("UPDATE OR DELETE", "ROW"), ("TRUNCATE", "STATEMENT")):
        name = "tr_source_fact_receipt_" + level.lower()
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {TABLE} "
            f"FOR EACH {level} EXECUTE FUNCTION refuse_source_fact_verification_mutation()"
        )


def downgrade() -> None:
    # A transaction-scoped exclusive lock makes the empty check race-safe.
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM {TABLE}) THEN
            RAISE EXCEPTION 'SOURCE_FACT_VERIFICATION_DOWNGRADE_NONEMPTY';
        END IF;
    END $$""")
    op.drop_table(TABLE)
    op.execute("DROP FUNCTION refuse_source_fact_verification_mutation()")
