"""Retain optional supplier lineage without inventing historical source facts.

Revision ID: c186b2c3d547
Revises: c185b2c3d546
"""

import sqlalchemy as sa

from alembic import op

revision = "c186b2c3d547"
down_revision = "c185b2c3d546"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transactions", sa.Column("source_record_id", sa.String(256), nullable=True))
    op.add_column("transactions", sa.Column("source_batch_id", sa.String(256), nullable=True))
    op.add_column(
        "transactions", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_transactions_source_batch", "transactions", ["source_system", "source_batch_id"]
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("transaction_batch_lineage", sa.JSON(none_as_null=True), nullable=True),
    )
    op.execute("""
        CREATE FUNCTION refuse_transaction_supplier_lineage_update() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            IF ROW(NEW.source_record_id, NEW.source_batch_id, NEW.observed_at)
               IS DISTINCT FROM ROW(OLD.source_record_id, OLD.source_batch_id, OLD.observed_at)
               OR NEW.source_system IS DISTINCT FROM OLD.source_system THEN
                RAISE EXCEPTION 'Accepted transaction supplier lineage is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER transactions_supplier_lineage_immutable
        BEFORE UPDATE OF source_system, source_record_id, source_batch_id, observed_at
        ON transactions
        FOR EACH ROW EXECUTE FUNCTION refuse_transaction_supplier_lineage_update();
    """)


def downgrade():
    connection = op.get_bind()
    retained = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM transactions WHERE source_record_id IS NOT NULL "
            "OR source_batch_id IS NOT NULL OR observed_at IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM ingestion_jobs WHERE transaction_batch_lineage IS NOT NULL)"
        )
    )
    if retained:
        raise RuntimeError("Supplier lineage is retained; downgrade would destroy source evidence")
    op.execute("DROP TRIGGER transactions_supplier_lineage_immutable ON transactions")
    op.execute("DROP FUNCTION refuse_transaction_supplier_lineage_update()")
    op.drop_column("ingestion_jobs", "transaction_batch_lineage")
    op.drop_index("ix_transactions_source_batch", table_name="transactions")
    for name in ("observed_at", "source_batch_id", "source_record_id"):
        op.drop_column("transactions", name)
