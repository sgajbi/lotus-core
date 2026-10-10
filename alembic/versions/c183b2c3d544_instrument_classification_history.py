"""Retain immutable instrument classification cuts.

Revision ID: c183b2c3d544
Revises: c181b2c3d542
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "c183b2c3d544"
down_revision = "c181b2c3d542"
branch_labels = None
depends_on = None
TABLE = "instrument_classification_cuts"
SCOPE = ("producer_id", "classification_set_id", "source_record_id")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("cut_id", sa.String(71), primary_key=True),
        sa.Column("content_hash", sa.String(71), nullable=False),
        *(sa.Column(name, sa.String(128), nullable=False) for name in SCOPE),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("predecessor_cut_id", sa.String(71)),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(*SCOPE, "source_version"),
        sa.UniqueConstraint(*SCOPE, "cut_id"),
        sa.UniqueConstraint("predecessor_cut_id"),
        sa.ForeignKeyConstraint(
            [*SCOPE, "predecessor_cut_id"], [f"{TABLE}.{name}" for name in (*SCOPE, "cut_id")]
        ),
        sa.CheckConstraint(
            "source_version > 0 AND ((source_version = 1) = (predecessor_cut_id IS NULL))"
        ),
        sa.CheckConstraint(
            "cut_id ~ '^sha256:[0-9a-f]{64}$' AND content_hash ~ '^sha256:[0-9a-f]{64}$'"
        ),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object' AND isfinite(received_at)"),
    )
    op.execute("""CREATE FUNCTION refuse_classification_cut_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ DECLARE populated boolean; BEGIN
            IF TG_OP = 'TRUNCATE' THEN
                IF current_setting('transaction_isolation') <> 'read committed' THEN
                    RAISE EXCEPTION 'CLASSIFICATION_CUT_TRUNCATE_ISOLATION';
                END IF;
                EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I)',
                               TG_TABLE_SCHEMA, TG_TABLE_NAME) INTO populated;
                IF NOT populated THEN RETURN NULL; END IF;
            END IF;
            RAISE EXCEPTION 'CLASSIFICATION_CUT_IMMUTABLE'; END $$""")
    for event, level in (("UPDATE OR DELETE", "ROW"), ("TRUNCATE", "STATEMENT")):
        op.execute(
            f"CREATE TRIGGER tr_classification_cut_{level.lower()} BEFORE {event} ON {TABLE} "
            f"FOR EACH {level} EXECUTE FUNCTION refuse_classification_cut_mutation()"
        )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SHOW transaction_isolation")) != "read committed":
        raise RuntimeError("CLASSIFICATION_CUT_DOWNGRADE_ISOLATION")
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM {TABLE}) THEN
        RAISE EXCEPTION 'CLASSIFICATION_CUT_DOWNGRADE_NONEMPTY'; END IF; END $$""")
    op.drop_table(TABLE)
    op.execute("DROP FUNCTION refuse_classification_cut_mutation()")
