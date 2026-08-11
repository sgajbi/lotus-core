"""Add durable lease-fenced corporate-action execution releases.

Revision ID: c153b2c3d520
Revises: c152b2c3d519
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c153b2c3d520"
down_revision: str | Sequence[str] | None = "c152b2c3d519"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist frozen release authority and ordered member progress."""

    op.add_column(
        "corporate_action_child_observations",
        sa.Column("transaction_payload_fingerprint", sa.String(length=71), nullable=True),
    )
    op.create_check_constraint(
        "ck_ca_observation_transaction_fingerprint",
        "corporate_action_child_observations",
        "transaction_payload_fingerprint IS NULL OR "
        "transaction_payload_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
    )

    op.create_table(
        "corporate_action_execution_releases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("readiness_evaluation_id", sa.Integer(), nullable=False),
        sa.Column("structural_plan_content_hash", sa.String(length=64), nullable=False),
        sa.Column("release_authority_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "next_execution_ordinal",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fence_token", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "structural_plan_content_hash ~ '^[0-9a-f]{64}$' "
            "AND release_authority_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ca_execution_release_hashes",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETE', 'FAILED')",
            name="ck_ca_execution_release_status",
        ),
        sa.CheckConstraint(
            "member_count > 0 AND next_execution_ordinal >= 0 "
            "AND next_execution_ordinal <= member_count "
            "AND attempt_count >= 0 AND fence_token >= 0",
            name="ck_ca_execution_release_counters",
        ),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="ck_ca_execution_release_lease_complete",
        ),
        sa.CheckConstraint(
            "lease_owner IS NULL OR "
            "(lease_owner = btrim(lease_owner) AND lease_owner <> '')",
            name="ck_ca_execution_release_owner_normalized",
        ),
        sa.CheckConstraint(
            "lease_token IS NULL OR lease_token ~ '^[0-9a-f]{64}$'",
            name="ck_ca_execution_release_lease_token",
        ),
        sa.CheckConstraint(
            "lease_expires_at IS NULL OR "
            "lease_expires_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_execution_release_lease_expiry_finite",
        ),
        sa.CheckConstraint(
            "(status = 'PROCESSING' AND lease_owner IS NOT NULL "
            "AND completed_at IS NULL AND failure_reason IS NULL) OR "
            "(status = 'PENDING' AND lease_owner IS NULL "
            "AND completed_at IS NULL AND failure_reason IS NULL) OR "
            "(status = 'COMPLETE' AND lease_owner IS NULL "
            "AND next_execution_ordinal = member_count "
            "AND completed_at IS NOT NULL AND failure_reason IS NULL) OR "
            "(status = 'FAILED' AND lease_owner IS NULL "
            "AND completed_at IS NULL AND failure_reason IS NOT NULL)",
            name="ck_ca_execution_release_state_shape",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR "
            "completed_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_execution_release_completed_finite",
        ),
        sa.ForeignKeyConstraint(
            ["readiness_evaluation_id"],
            ["corporate_action_readiness_evaluations.id"],
            name="fk_ca_execution_release_readiness",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "readiness_evaluation_id",
            name="uq_ca_execution_release_readiness",
        ),
        sa.UniqueConstraint(
            "release_authority_hash",
            name="uq_ca_execution_release_authority",
        ),
    )
    op.create_index(
        "ix_ca_execution_release_claim",
        "corporate_action_execution_releases",
        ["status", "lease_expires_at", "id"],
    )

    op.create_table(
        "corporate_action_execution_members",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("release_id", sa.BigInteger(), nullable=False),
        sa.Column("execution_ordinal", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=False),
        sa.Column("transaction_epoch", sa.Integer(), nullable=False),
        sa.Column("observed_child_content_hash", sa.String(length=64), nullable=False),
        sa.Column("transaction_payload_fingerprint", sa.String(length=71), nullable=False),
        sa.Column("status", sa.String(), server_default="PENDING", nullable=False),
        sa.Column("completed_fence_token", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "execution_ordinal >= 0",
            name="ck_ca_execution_member_ordinal",
        ),
        sa.CheckConstraint(
            "transaction_id = btrim(transaction_id) AND transaction_id <> ''",
            name="ck_ca_execution_member_transaction_normalized",
        ),
        sa.CheckConstraint(
            "transaction_epoch >= 0",
            name="ck_ca_execution_member_epoch",
        ),
        sa.CheckConstraint(
            "observed_child_content_hash ~ '^[0-9a-f]{64}$' "
            "AND transaction_payload_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_ca_execution_member_hashes",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETE')",
            name="ck_ca_execution_member_status",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND completed_fence_token IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'COMPLETE' AND completed_fence_token > 0 "
            "AND completed_at IS NOT NULL)",
            name="ck_ca_execution_member_state_shape",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR "
            "completed_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_execution_member_completed_finite",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["corporate_action_execution_releases.id"],
            name="fk_ca_execution_member_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.transaction_id"],
            name="fk_ca_execution_member_transaction",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["corporate_action_child_observations.id"],
            name="fk_ca_execution_member_observation",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "release_id",
            "execution_ordinal",
            name="uq_ca_execution_member_ordinal",
        ),
        sa.UniqueConstraint(
            "release_id",
            "transaction_id",
            name="uq_ca_execution_member_transaction",
        ),
        sa.UniqueConstraint(
            "release_id",
            "observation_id",
            name="uq_ca_execution_member_observation",
        ),
    )
    op.create_index(
        "ix_ca_execution_member_pending",
        "corporate_action_execution_members",
        ["release_id", "status", "execution_ordinal"],
    )
    op.create_index(
        "ix_ca_execution_member_transaction",
        "corporate_action_execution_members",
        ["transaction_id"],
    )

    op.execute(
        sa.text(
            """
            CREATE FUNCTION enforce_ca_execution_release_identity()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF ROW(
                    NEW.readiness_evaluation_id,
                    NEW.structural_plan_content_hash,
                    NEW.release_authority_hash,
                    NEW.member_count,
                    NEW.created_at
                ) IS DISTINCT FROM ROW(
                    OLD.readiness_evaluation_id,
                    OLD.structural_plan_content_hash,
                    OLD.release_authority_hash,
                    OLD.member_count,
                    OLD.created_at
                ) THEN
                    RAISE EXCEPTION 'corporate-action execution release authority is immutable'
                        USING ERRCODE = '23514';
                END IF;
                IF NEW.next_execution_ordinal < OLD.next_execution_ordinal
                   OR NEW.attempt_count < OLD.attempt_count
                   OR NEW.fence_token < OLD.fence_token THEN
                    RAISE EXCEPTION 'corporate-action execution release progress is monotonic'
                        USING ERRCODE = '23514';
                END IF;
                IF OLD.status IN ('COMPLETE', 'FAILED') AND NEW IS DISTINCT FROM OLD THEN
                    RAISE EXCEPTION 'corporate-action execution terminal state is immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER trg_ca_execution_release_identity
            BEFORE UPDATE ON corporate_action_execution_releases
            FOR EACH ROW
            EXECUTE FUNCTION enforce_ca_execution_release_identity();

            CREATE FUNCTION enforce_ca_execution_member_identity()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF ROW(
                    NEW.release_id,
                    NEW.execution_ordinal,
                    NEW.transaction_id,
                    NEW.observation_id,
                    NEW.transaction_epoch,
                    NEW.observed_child_content_hash,
                    NEW.transaction_payload_fingerprint,
                    NEW.created_at
                ) IS DISTINCT FROM ROW(
                    OLD.release_id,
                    OLD.execution_ordinal,
                    OLD.transaction_id,
                    OLD.observation_id,
                    OLD.transaction_epoch,
                    OLD.observed_child_content_hash,
                    OLD.transaction_payload_fingerprint,
                    OLD.created_at
                ) THEN
                    RAISE EXCEPTION 'corporate-action execution member authority is immutable'
                        USING ERRCODE = '23514';
                END IF;
                IF OLD.status = 'COMPLETE' AND NEW IS DISTINCT FROM OLD THEN
                    RAISE EXCEPTION 'corporate-action execution member completion is immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER trg_ca_execution_member_identity
            BEFORE UPDATE ON corporate_action_execution_members
            FOR EACH ROW
            EXECUTE FUNCTION enforce_ca_execution_member_identity();
            """
        )
    )


def downgrade() -> None:
    """Remove corporate-action execution release persistence."""

    op.execute(sa.text("DROP FUNCTION enforce_ca_execution_member_identity() CASCADE"))
    op.execute(sa.text("DROP FUNCTION enforce_ca_execution_release_identity() CASCADE"))
    op.drop_table("corporate_action_execution_members")
    op.drop_table("corporate_action_execution_releases")
    op.drop_constraint(
        "ck_ca_observation_transaction_fingerprint",
        "corporate_action_child_observations",
        type_="check",
    )
    op.drop_column(
        "corporate_action_child_observations",
        "transaction_payload_fingerprint",
    )
