"""Append source-confirmation facts without rewriting economic transaction history.

Revision ID: c177b2c3d538
Revises: c176b2c3d537
Create Date: 2026-10-05

Existing pending/terminal transactions, raw events and receipts remain untouched.
The new table starts empty: absence of a revision never fabricates qualification.
Downgrade is supported only before any durable revision has been committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c177b2c3d538"
down_revision: str | Sequence[str] | None = "c176b2c3d537"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "transaction_source_revisions"
_HASH_FIELDS = (
    "root_raw_sha256",
    "expected_head_sha256",
    "canonical_request_sha256",
    "attestation_sha256",
    "original_output_sha256",
    "revision_sha256",
)


def _columns() -> list[sa.Column]:
    return [
        sa.Column("revision_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column(
            "root_raw_event_id", sa.Integer(), sa.ForeignKey("outbox_events.id"), nullable=False
        ),
        sa.Column("predecessor_revision_id", sa.String(128), nullable=True),
        sa.Column("expected_head_id", sa.String(128), nullable=False),
        sa.Column("command_id", sa.String(128), nullable=False),
        sa.Column("operation_id", sa.String(128), nullable=False),
        *(sa.Column(name, sa.String(64), nullable=False) for name in _HASH_FIELDS),
        sa.Column("source_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("source_base", sa.Numeric(18, 10), nullable=False),
        sa.Column("original_local_present", sa.Boolean(), nullable=False),
        sa.Column("original_base_present", sa.Boolean(), nullable=False),
        sa.Column("qualification_receipt", sa.JSON(), nullable=False),
        sa.Column("authorization_claims", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(512), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column(
            "confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _constraints() -> list[sa.Constraint]:
    identity = [
        "revision_id",
        "tenant_id",
        "transaction_id",
        "root_raw_event_id",
        "revision_sha256",
    ]
    return [
        sa.ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_source_revision_portfolio_owner",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "portfolio_id"],
            ["transactions.transaction_id", "transactions.portfolio_id"],
            name="fk_source_revision_transaction_owner",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "operation_id"],
            ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"],
            name="fk_source_revision_operation_owner",
        ),
        sa.UniqueConstraint("tenant_id", "command_id", name="uq_source_revision_command"),
        sa.UniqueConstraint("tenant_id", "operation_id", name="uq_source_revision_operation"),
        sa.UniqueConstraint(*identity, name="uq_source_revision_chain_identity"),
        sa.ForeignKeyConstraint(
            [
                "predecessor_revision_id",
                "tenant_id",
                "transaction_id",
                "root_raw_event_id",
                "expected_head_sha256",
            ],
            [f"{_TABLE}.{name}" for name in identity],
            name="fk_source_revision_same_chain_predecessor",
        ),
        sa.UniqueConstraint("predecessor_revision_id", name="uq_source_revision_child"),
        sa.CheckConstraint(
            "predecessor_revision_id IS NULL OR predecessor_revision_id <> revision_id",
            name="ck_source_revision_not_self",
        ),
        sa.CheckConstraint(
            "expected_head_id = coalesce(predecessor_revision_id, root_raw_event_id::text)",
            name="ck_source_revision_expected_head",
        ),
        sa.CheckConstraint(
            "predecessor_revision_id IS NOT NULL OR expected_head_sha256 = root_raw_sha256",
            name="ck_source_revision_root_head_hash",
        ),
        sa.CheckConstraint(
            "NOT original_local_present OR NOT original_base_present",
            name="ck_source_revision_original_incomplete",
        ),
        sa.CheckConstraint(
            "(original_local_present OR source_local = 0) AND "
            "(original_base_present OR source_base = 0)",
            name="ck_source_revision_missing_confirmation_zero",
        ),
        *(
            sa.CheckConstraint(f"{name} ~ '^[0-9a-f]{{64}}$'", name=f"ck_source_revision_{name}")
            for name in _HASH_FIELDS
        ),
        *(
            sa.CheckConstraint(
                f"length(btrim({name})) > 0", name=f"ck_source_revision_{name}_nonblank"
            )
            for name in (
                "revision_id",
                "command_id",
                "operation_id",
                "reason",
                "correlation_id",
                "trace_id",
            )
        ),
        *(
            sa.CheckConstraint(
                f"CAST(source_{basis} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
                name=f"ck_source_revision_{basis}_finite",
            )
            for basis in ("local", "base")
        ),
    ]


def upgrade() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.create_unique_constraint(
        "uq_transaction_source_revision_owner", "transactions", ["transaction_id", "portfolio_id"]
    )
    op.create_table(_TABLE, *_columns(), *_constraints())
    op.create_index(
        "uq_source_revision_initial",
        _TABLE,
        ["tenant_id", "transaction_id"],
        unique=True,
        postgresql_where=sa.text("predecessor_revision_id IS NULL"),
    )
    op.execute(
        sa.text("""
        CREATE FUNCTION reject_transaction_source_revision_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION USING ERRCODE = '55000',
                MESSAGE = 'Committed source revisions are immutable; append or forward-fix';
        END $$
    """)
    )
    op.execute(
        sa.text(f"""
        CREATE TRIGGER transaction_source_revision_immutable
        BEFORE UPDATE OR DELETE ON {_TABLE}
        FOR EACH ROW EXECUTE FUNCTION reject_transaction_source_revision_mutation()
    """)
    )


def downgrade() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute(sa.text(f"LOCK TABLE {_TABLE} IN ACCESS EXCLUSIVE MODE"))
    op.execute(
        sa.text(f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM {_TABLE}) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                    MESSAGE = 'Durable source history blocks downgrade; restore or forward-fix';
            END IF;
        END $$
    """)
    )
    op.drop_table(_TABLE)
    op.execute(sa.text("DROP FUNCTION reject_transaction_source_revision_mutation()"))
    op.drop_constraint("uq_transaction_source_revision_owner", "transactions", type_="unique")
