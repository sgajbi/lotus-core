"""Persist book-scoped corporate-action parent graphs and readiness evidence.

Revision ID: c152b2c3d519
Revises: c151b2c3d518
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c152b2c3d519"
down_revision: str | Sequence[str] | None = "c151b2c3d518"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_immutable_ledger_trigger(table_name: str, trigger_suffix: str) -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER trg_ca_{trigger_suffix}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION reject_ca_ledger_mutation();
            """
        )
    )


def upgrade() -> None:
    """Add normalized parent, graph, observation and readiness history."""

    op.execute(
        sa.text(
            """
            CREATE FUNCTION reject_ca_ledger_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'corporate-action ledger rows are immutable'
                    USING ERRCODE = '23514';
            END;
            $$;
            """
        )
    )

    op.create_table(
        "corporate_action_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("legal_book_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("corporate_action_event_id", sa.String(), nullable=False),
        sa.Column("linked_transaction_group_id", sa.String(), nullable=False),
        sa.Column("parent_event_reference", sa.String(), nullable=False),
        sa.Column("current_manifest_version", sa.Integer(), nullable=True),
        sa.Column(
            "last_observation_sequence",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("state_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "readiness_status",
            sa.String(),
            server_default=sa.text("'AWAITING_MANIFEST'"),
            nullable=False,
        ),
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
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND legal_book_id = btrim(legal_book_id) AND legal_book_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND corporate_action_event_id = btrim(corporate_action_event_id) "
            "AND corporate_action_event_id <> '' "
            "AND linked_transaction_group_id = btrim(linked_transaction_group_id) "
            "AND linked_transaction_group_id <> '' "
            "AND parent_event_reference = btrim(parent_event_reference) "
            "AND parent_event_reference <> ''",
            name="ck_ca_event_identity_normalized",
        ),
        sa.CheckConstraint(
            "current_manifest_version IS NULL OR current_manifest_version >= 1",
            name="ck_ca_event_manifest_version",
        ),
        sa.CheckConstraint(
            "last_observation_sequence >= 0 AND state_version >= 0",
            name="ck_ca_event_counters_nonnegative",
        ),
        sa.CheckConstraint(
            "readiness_status IN ('AWAITING_MANIFEST', 'AWAITING_COMPLETION', "
            "'AWAITING_CHILDREN', 'INVALID', 'READY')",
            name="ck_ca_event_readiness_status",
        ),
        sa.CheckConstraint(
            "(current_manifest_version IS NULL AND readiness_status = 'AWAITING_MANIFEST') "
            "OR (current_manifest_version IS NOT NULL "
            "AND readiness_status <> 'AWAITING_MANIFEST')",
            name="ck_ca_event_manifest_status_shape",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "legal_book_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.legal_book_id", "portfolios.portfolio_id"],
            name="fk_ca_event_book_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "corporate_action_event_id",
            name="uq_ca_event_portfolio_identity",
        ),
        sa.UniqueConstraint(
            "portfolio_id",
            "linked_transaction_group_id",
            "parent_event_reference",
            name="uq_ca_event_parent_group",
        ),
    )
    op.create_index(
        "ix_ca_event_portfolio_status_updated",
        "corporate_action_events",
        ["portfolio_id", "readiness_status", sa.text("updated_at DESC")],
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION enforce_ca_event_identity_immutable()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF ROW(
                    NEW.tenant_id,
                    NEW.legal_book_id,
                    NEW.portfolio_id,
                    NEW.corporate_action_event_id,
                    NEW.linked_transaction_group_id,
                    NEW.parent_event_reference,
                    NEW.created_at
                ) IS DISTINCT FROM ROW(
                    OLD.tenant_id,
                    OLD.legal_book_id,
                    OLD.portfolio_id,
                    OLD.corporate_action_event_id,
                    OLD.linked_transaction_group_id,
                    OLD.parent_event_reference,
                    OLD.created_at
                ) THEN
                    RAISE EXCEPTION 'corporate-action event identity is immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER trg_ca_event_identity_immutable
            BEFORE UPDATE ON corporate_action_events
            FOR EACH ROW
            EXECUTE FUNCTION enforce_ca_event_identity_immutable();
            """
        )
    )

    op.create_table(
        "corporate_action_manifest_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("manifest_version", sa.Integer(), nullable=False),
        sa.Column("corporate_action_type", sa.String(), nullable=False),
        sa.Column("completion_declared", sa.Boolean(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=False),
        sa.Column("source_revision", sa.String(), nullable=False),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("manifest_content_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_manifest_id", sa.Integer(), nullable=True),
        sa.Column("previous_manifest_content_hash", sa.String(length=64), nullable=True),
        sa.Column("expected_node_count", sa.Integer(), nullable=False),
        sa.Column("expected_edge_count", sa.Integer(), nullable=False),
        sa.Column("opened_observation_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "manifest_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "manifest_version >= 1 AND expected_node_count >= 0 "
            "AND expected_edge_count >= 0 AND opened_observation_sequence >= 0",
            name="ck_ca_manifest_counts",
        ),
        sa.CheckConstraint(
            "corporate_action_type = btrim(corporate_action_type) "
            "AND corporate_action_type <> '' "
            "AND source_system = btrim(source_system) AND source_system <> '' "
            "AND source_record_id = btrim(source_record_id) AND source_record_id <> '' "
            "AND source_revision = btrim(source_revision) AND source_revision <> ''",
            name="ck_ca_manifest_identity_normalized",
        ),
        sa.CheckConstraint(
            "source_content_hash ~ '^[0-9a-f]{64}$' "
            "AND manifest_content_hash ~ '^[0-9a-f]{64}$' "
            "AND (previous_manifest_content_hash IS NULL "
            "OR previous_manifest_content_hash ~ '^[0-9a-f]{64}$')",
            name="ck_ca_manifest_hashes",
        ),
        sa.CheckConstraint(
            "(manifest_version = 1 AND previous_manifest_id IS NULL "
            "AND previous_manifest_content_hash IS NULL) "
            "OR (manifest_version > 1 AND previous_manifest_id IS NOT NULL "
            "AND previous_manifest_content_hash IS NOT NULL)",
            name="ck_ca_manifest_chain_shape",
        ),
        sa.CheckConstraint(
            "source_observed_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_manifest_observed_at_finite",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(manifest_payload) = 'object'",
            name="ck_ca_manifest_payload_object",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["corporate_action_events.id"],
            name="fk_ca_manifest_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "previous_manifest_id"],
            [
                "corporate_action_manifest_versions.event_id",
                "corporate_action_manifest_versions.id",
            ],
            name="fk_ca_manifest_predecessor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "id", name="uq_ca_manifest_event_record"),
        sa.UniqueConstraint(
            "event_id",
            "manifest_version",
            name="uq_ca_manifest_event_version",
        ),
        sa.UniqueConstraint(
            "event_id",
            "source_system",
            "source_record_id",
            "source_revision",
            name="uq_ca_manifest_source_revision",
        ),
        sa.UniqueConstraint(
            "event_id",
            "manifest_content_hash",
            name="uq_ca_manifest_event_content",
        ),
    )
    _create_immutable_ledger_trigger("corporate_action_manifest_versions", "manifest_version")
    op.create_index(
        "ix_ca_manifest_source_history",
        "corporate_action_manifest_versions",
        ["source_system", "source_record_id", "source_revision"],
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION enforce_ca_manifest_predecessor()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                predecessor_version integer;
                predecessor_hash varchar(64);
            BEGIN
                IF NEW.manifest_version = 1 THEN
                    RETURN NEW;
                END IF;

                SELECT manifest_version, manifest_content_hash
                INTO predecessor_version, predecessor_hash
                FROM corporate_action_manifest_versions
                WHERE id = NEW.previous_manifest_id
                  AND event_id = NEW.event_id;

                IF predecessor_version IS NULL
                   OR predecessor_version <> NEW.manifest_version - 1
                   OR predecessor_hash <> NEW.previous_manifest_content_hash THEN
                    RAISE EXCEPTION
                        'corporate-action manifest predecessor does not continue the event chain'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER trg_ca_manifest_predecessor
            BEFORE INSERT OR UPDATE ON corporate_action_manifest_versions
            FOR EACH ROW
            EXECUTE FUNCTION enforce_ca_manifest_predecessor();
            """
        )
    )
    op.create_foreign_key(
        "fk_ca_event_current_manifest",
        "corporate_action_events",
        "corporate_action_manifest_versions",
        ["id", "current_manifest_version"],
        ["event_id", "manifest_version"],
    )

    op.create_table(
        "corporate_action_manifest_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("transaction_type", sa.String(), nullable=False),
        sa.Column("child_role", sa.String(), nullable=False),
        sa.Column("child_sequence_hint", sa.Integer(), nullable=True),
        sa.Column("instrument_id", sa.String(), nullable=True),
        sa.Column("source_instrument_id", sa.String(), nullable=True),
        sa.Column("target_instrument_id", sa.String(), nullable=True),
        sa.Column("child_content_hash", sa.String(length=64), nullable=False),
        sa.Column("resolved_execution_ordinal", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "transaction_id = btrim(transaction_id) AND transaction_id <> '' "
            "AND transaction_type = btrim(transaction_type) AND transaction_type <> '' "
            "AND child_role = btrim(child_role) AND child_role <> ''",
            name="ck_ca_manifest_node_normalized",
        ),
        sa.CheckConstraint(
            "(instrument_id IS NULL OR "
            "(instrument_id = btrim(instrument_id) AND instrument_id <> '')) "
            "AND (source_instrument_id IS NULL OR "
            "(source_instrument_id = btrim(source_instrument_id) "
            "AND source_instrument_id <> '')) "
            "AND (target_instrument_id IS NULL OR "
            "(target_instrument_id = btrim(target_instrument_id) "
            "AND target_instrument_id <> ''))",
            name="ck_ca_manifest_node_instruments",
        ),
        sa.CheckConstraint(
            "child_sequence_hint IS NULL OR child_sequence_hint >= 0",
            name="ck_ca_manifest_node_sequence",
        ),
        sa.CheckConstraint(
            "resolved_execution_ordinal IS NULL OR resolved_execution_ordinal >= 0",
            name="ck_ca_manifest_node_ordinal",
        ),
        sa.CheckConstraint(
            "child_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ca_manifest_node_hash",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["corporate_action_manifest_versions.id"],
            name="fk_ca_manifest_node_manifest",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "manifest_id",
            "transaction_id",
            name="uq_ca_manifest_node_identity",
        ),
    )
    _create_immutable_ledger_trigger("corporate_action_manifest_nodes", "manifest_node")
    op.create_index(
        "ix_ca_manifest_node_order",
        "corporate_action_manifest_nodes",
        ["manifest_id", "resolved_execution_ordinal", "transaction_id"],
    )
    op.create_index(
        "ix_ca_manifest_node_transaction",
        "corporate_action_manifest_nodes",
        ["transaction_id"],
    )
    op.create_index(
        "uq_ca_manifest_node_resolved_ordinal",
        "corporate_action_manifest_nodes",
        ["manifest_id", "resolved_execution_ordinal"],
        unique=True,
        postgresql_where=sa.text("resolved_execution_ordinal IS NOT NULL"),
    )

    op.create_table(
        "corporate_action_manifest_edges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=False),
        sa.Column("predecessor_transaction_id", sa.String(), nullable=False),
        sa.Column("successor_transaction_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "predecessor_transaction_id <> successor_transaction_id",
            name="ck_ca_manifest_edge_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["corporate_action_manifest_versions.id"],
            name="fk_ca_manifest_edge_manifest",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id", "predecessor_transaction_id"],
            [
                "corporate_action_manifest_nodes.manifest_id",
                "corporate_action_manifest_nodes.transaction_id",
            ],
            name="fk_ca_edge_predecessor_node",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id", "successor_transaction_id"],
            [
                "corporate_action_manifest_nodes.manifest_id",
                "corporate_action_manifest_nodes.transaction_id",
            ],
            name="fk_ca_edge_successor_node",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "manifest_id",
            "predecessor_transaction_id",
            "successor_transaction_id",
            name="uq_ca_manifest_edge",
        ),
    )
    _create_immutable_ledger_trigger("corporate_action_manifest_edges", "manifest_edge")
    op.create_index(
        "ix_ca_manifest_edge_successor",
        "corporate_action_manifest_edges",
        ["manifest_id", "successor_transaction_id"],
    )
    op.create_table(
        "corporate_action_child_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("observation_sequence", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("transaction_epoch", sa.Integer(), nullable=False),
        sa.Column("delivery_event_id", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("observed_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "observed_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "observation_sequence >= 1 AND transaction_epoch >= 0",
            name="ck_ca_observation_counters",
        ),
        sa.CheckConstraint(
            "delivery_event_id = btrim(delivery_event_id) AND delivery_event_id <> '' "
            "AND transaction_id = btrim(transaction_id) AND transaction_id <> ''",
            name="ck_ca_observation_identity_normalized",
        ),
        sa.CheckConstraint(
            "observed_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ca_observation_hash",
        ),
        sa.CheckConstraint(
            "observed_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_observation_observed_at_finite",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(observed_payload) = 'object'",
            name="ck_ca_observation_payload_object",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["corporate_action_events.id"],
            name="fk_ca_observation_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.transaction_id"],
            name="fk_ca_observation_transaction",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "observation_sequence",
            name="uq_ca_observation_sequence",
        ),
        sa.UniqueConstraint(
            "event_id",
            "delivery_event_id",
            name="uq_ca_observation_delivery",
        ),
        sa.UniqueConstraint(
            "event_id",
            "transaction_id",
            "transaction_epoch",
            "observed_content_hash",
            name="uq_ca_observation_semantic_retry",
        ),
    )
    _create_immutable_ledger_trigger("corporate_action_child_observations", "child_observation")
    op.create_index(
        "ix_ca_observation_event_transaction",
        "corporate_action_child_observations",
        [
            "event_id",
            "transaction_id",
            sa.text("transaction_epoch DESC"),
            sa.text("observation_sequence DESC"),
        ],
    )
    op.create_index(
        "ix_ca_observation_transaction",
        "corporate_action_child_observations",
        ["transaction_id"],
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION enforce_ca_observation_book_scope()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM corporate_action_events AS event
                    JOIN transactions AS transaction
                      ON transaction.transaction_id = NEW.transaction_id
                     AND transaction.portfolio_id = event.portfolio_id
                    WHERE event.id = NEW.event_id
                ) THEN
                    RAISE EXCEPTION
                        'corporate-action observation transaction is outside event portfolio'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER trg_ca_observation_book_scope
            BEFORE INSERT OR UPDATE ON corporate_action_child_observations
            FOR EACH ROW
            EXECUTE FUNCTION enforce_ca_observation_book_scope();
            """
        )
    )

    op.create_table(
        "corporate_action_readiness_evaluations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.Integer(), nullable=True),
        sa.Column("through_observation_sequence", sa.Integer(), nullable=False),
        sa.Column("readiness_status", sa.String(), nullable=False),
        sa.Column("manifest_content_hash", sa.String(length=64), nullable=True),
        sa.Column("execution_plan_content_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "findings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "ordered_transaction_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state_version >= 1 AND through_observation_sequence >= 0",
            name="ck_ca_readiness_counters",
        ),
        sa.CheckConstraint(
            "readiness_status IN ('AWAITING_MANIFEST', 'AWAITING_COMPLETION', "
            "'AWAITING_CHILDREN', 'INVALID', 'READY')",
            name="ck_ca_readiness_status",
        ),
        sa.CheckConstraint(
            "(manifest_content_hash IS NULL OR manifest_content_hash ~ '^[0-9a-f]{64}$') "
            "AND (execution_plan_content_hash IS NULL "
            "OR execution_plan_content_hash ~ '^[0-9a-f]{64}$')",
            name="ck_ca_readiness_hashes",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(findings) = 'array' AND jsonb_typeof(ordered_transaction_ids) = 'array'",
            name="ck_ca_readiness_evidence_arrays",
        ),
        sa.CheckConstraint(
            "(manifest_id IS NULL AND readiness_status = 'AWAITING_MANIFEST' "
            "AND manifest_content_hash IS NULL) "
            "OR (manifest_id IS NOT NULL AND readiness_status <> 'AWAITING_MANIFEST' "
            "AND manifest_content_hash IS NOT NULL)",
            name="ck_ca_readiness_manifest_shape",
        ),
        sa.CheckConstraint(
            "(readiness_status = 'READY' AND execution_plan_content_hash IS NOT NULL "
            "AND jsonb_array_length(findings) = 0 "
            "AND jsonb_array_length(ordered_transaction_ids) > 0) "
            "OR (readiness_status <> 'READY' AND execution_plan_content_hash IS NULL "
            "AND jsonb_array_length(ordered_transaction_ids) = 0)",
            name="ck_ca_readiness_ready_shape",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["corporate_action_events.id"],
            name="fk_ca_readiness_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "manifest_id"],
            [
                "corporate_action_manifest_versions.event_id",
                "corporate_action_manifest_versions.id",
            ],
            name="fk_ca_readiness_event_manifest",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "state_version",
            name="uq_ca_readiness_state_version",
        ),
    )
    _create_immutable_ledger_trigger(
        "corporate_action_readiness_evaluations", "readiness_evaluation"
    )
    op.create_index(
        "ix_ca_readiness_status_created",
        "corporate_action_readiness_evaluations",
        ["readiness_status", sa.text("created_at DESC")],
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION enforce_ca_readiness_plan()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                expected_order jsonb;
                expected_count integer;
                resolved_count integer;
                minimum_ordinal integer;
                maximum_ordinal integer;
                declared_node_count integer;
                actual_edge_count integer;
                declared_edge_count integer;
                invalid_edge_count integer;
                observed_node_count integer;
                mismatched_observation_count integer;
                unexpected_observation_count integer;
                event_observation_sequence integer;
                event_state_version integer;
                event_manifest_version integer;
                manifest_version integer;
                declared_manifest_content_hash text;
                completion_declared boolean;
                manifest_opened_observation_sequence integer;
                predecessor_manifest_id integer;
            BEGIN
                IF NEW.readiness_status <> 'READY' THEN
                    RETURN NEW;
                END IF;

                SELECT
                    COALESCE(
                        jsonb_agg(
                            node.transaction_id ORDER BY node.resolved_execution_ordinal
                        ) FILTER (WHERE node.id IS NOT NULL),
                        '[]'::jsonb
                    ),
                    count(node.id),
                    count(node.resolved_execution_ordinal),
                    min(node.resolved_execution_ordinal),
                    max(node.resolved_execution_ordinal),
                    manifest.expected_node_count,
                    manifest.opened_observation_sequence,
                    manifest.previous_manifest_id
                INTO
                    expected_order,
                    expected_count,
                    resolved_count,
                    minimum_ordinal,
                    maximum_ordinal,
                    declared_node_count,
                    manifest_opened_observation_sequence,
                    predecessor_manifest_id
                FROM corporate_action_manifest_versions AS manifest
                LEFT JOIN corporate_action_manifest_nodes AS node
                  ON node.manifest_id = manifest.id
                WHERE manifest.id = NEW.manifest_id
                  AND manifest.event_id = NEW.event_id
                GROUP BY
                    manifest.expected_node_count,
                    manifest.opened_observation_sequence,
                    manifest.previous_manifest_id;

                IF expected_count IS NULL
                   OR expected_count = 0
                   OR expected_count <> declared_node_count
                   OR resolved_count <> expected_count
                   OR minimum_ordinal <> 0
                   OR maximum_ordinal <> expected_count - 1
                   OR NEW.ordered_transaction_ids <> expected_order THEN
                    RAISE EXCEPTION
                        'corporate-action READY plan does not match manifest node order'
                        USING ERRCODE = '23514';
                END IF;

                SELECT
                    manifest.expected_edge_count,
                    manifest.manifest_version,
                    manifest.manifest_content_hash,
                    manifest.completion_declared,
                    count(edge.id),
                    count(edge.id) FILTER (
                        WHERE predecessor.resolved_execution_ordinal
                              >= successor.resolved_execution_ordinal
                    )
                INTO
                    declared_edge_count,
                    manifest_version,
                    declared_manifest_content_hash,
                    completion_declared,
                    actual_edge_count,
                    invalid_edge_count
                FROM corporate_action_manifest_versions AS manifest
                LEFT JOIN corporate_action_manifest_edges AS edge
                  ON edge.manifest_id = manifest.id
                LEFT JOIN corporate_action_manifest_nodes AS predecessor
                  ON predecessor.manifest_id = edge.manifest_id
                 AND predecessor.transaction_id = edge.predecessor_transaction_id
                LEFT JOIN corporate_action_manifest_nodes AS successor
                  ON successor.manifest_id = edge.manifest_id
                 AND successor.transaction_id = edge.successor_transaction_id
                WHERE manifest.id = NEW.manifest_id
                  AND manifest.event_id = NEW.event_id
                GROUP BY
                    manifest.expected_edge_count,
                    manifest.manifest_version,
                    manifest.manifest_content_hash,
                    manifest.completion_declared;

                IF actual_edge_count <> declared_edge_count
                   OR invalid_edge_count <> 0 THEN
                    RAISE EXCEPTION
                        'corporate-action READY plan does not match manifest edges'
                        USING ERRCODE = '23514';
                END IF;

                IF NEW.manifest_content_hash <> declared_manifest_content_hash
                   OR NOT completion_declared THEN
                    RAISE EXCEPTION
                        'corporate-action READY evidence does not match complete manifest'
                        USING ERRCODE = '23514';
                END IF;

                SELECT
                    event.last_observation_sequence,
                    event.state_version,
                    event.current_manifest_version
                INTO
                    event_observation_sequence,
                    event_state_version,
                    event_manifest_version
                FROM corporate_action_events AS event
                WHERE event.id = NEW.event_id;

                IF NEW.through_observation_sequence <> event_observation_sequence
                   OR NEW.state_version <> event_state_version
                   OR manifest_version <> event_manifest_version THEN
                    RAISE EXCEPTION
                        'corporate-action READY evidence is stale against event state'
                        USING ERRCODE = '23514';
                END IF;

                WITH latest_observation AS (
                    SELECT DISTINCT ON (observation.transaction_id)
                        observation.transaction_id,
                        observation.observed_content_hash
                    FROM corporate_action_child_observations AS observation
                    WHERE observation.event_id = NEW.event_id
                      AND observation.observation_sequence
                          <= NEW.through_observation_sequence
                      AND (
                          observation.observation_sequence
                              > manifest_opened_observation_sequence
                          OR (
                              EXISTS (
                                  SELECT 1
                                  FROM corporate_action_manifest_nodes AS expected_node
                                  WHERE expected_node.manifest_id = NEW.manifest_id
                                    AND expected_node.transaction_id
                                        = observation.transaction_id
                              )
                              AND EXISTS (
                                  SELECT 1
                                  FROM corporate_action_manifest_nodes AS predecessor_node
                                  WHERE predecessor_node.manifest_id = predecessor_manifest_id
                                    AND predecessor_node.transaction_id
                                        = observation.transaction_id
                              )
                          )
                      )
                    ORDER BY
                        observation.transaction_id,
                        observation.transaction_epoch DESC,
                        observation.observation_sequence DESC
                )
                SELECT
                    count(latest_observation.transaction_id),
                    count(*) FILTER (
                        WHERE latest_observation.transaction_id IS NULL
                           OR latest_observation.observed_content_hash
                              <> node.child_content_hash
                    ),
                    (
                        SELECT count(*)
                        FROM latest_observation AS unexpected_observation
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM corporate_action_manifest_nodes AS expected_node
                            WHERE expected_node.manifest_id = NEW.manifest_id
                              AND expected_node.transaction_id
                                  = unexpected_observation.transaction_id
                        )
                    )
                INTO
                    observed_node_count,
                    mismatched_observation_count,
                    unexpected_observation_count
                FROM corporate_action_manifest_nodes AS node
                LEFT JOIN latest_observation
                  ON latest_observation.transaction_id = node.transaction_id
                WHERE node.manifest_id = NEW.manifest_id;

                IF observed_node_count <> declared_node_count
                   OR mismatched_observation_count <> 0
                   OR unexpected_observation_count <> 0 THEN
                    RAISE EXCEPTION
                        'corporate-action READY evidence does not match latest child observations'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER trg_ca_readiness_plan
            BEFORE INSERT OR UPDATE ON corporate_action_readiness_evaluations
            FOR EACH ROW
            EXECUTE FUNCTION enforce_ca_readiness_plan();
            """
        )
    )


def downgrade() -> None:
    """Remove the inactive corporate-action parent-graph persistence model."""

    op.drop_table("corporate_action_readiness_evaluations")
    op.execute(sa.text("DROP FUNCTION enforce_ca_readiness_plan()"))
    op.drop_table("corporate_action_child_observations")
    op.execute(sa.text("DROP FUNCTION enforce_ca_observation_book_scope()"))
    op.drop_table("corporate_action_manifest_edges")
    op.drop_table("corporate_action_manifest_nodes")
    op.drop_constraint(
        "fk_ca_event_current_manifest",
        "corporate_action_events",
        type_="foreignkey",
    )
    op.drop_table("corporate_action_manifest_versions")
    op.execute(sa.text("DROP FUNCTION enforce_ca_manifest_predecessor()"))
    op.drop_table("corporate_action_events")
    op.execute(sa.text("DROP FUNCTION enforce_ca_event_identity_immutable()"))
    op.execute(sa.text("DROP FUNCTION reject_ca_ledger_mutation()"))
