"""Govern durable ingestion payload evidence and replay authority.

Revision ID: c157b2c3d524
Revises: c156b2c3d523
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c157b2c3d524"
down_revision: str | Sequence[str] | None = "c156b2c3d523"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECKS = {
    "ck_ingestion_jobs_payload_fingerprint_format": (
        "request_payload_fingerprint IS NULL OR "
        "request_payload_fingerprint ~ '^sha256:[0-9a-f]{64}$'"
    ),
    "ck_ingestion_jobs_payload_classification": (
        "request_payload_classification IN "
        "('internal', 'confidential', 'restricted', 'legacy_unclassified')"
    ),
    "ck_ingestion_jobs_payload_representation": (
        "request_payload_representation IN "
        "('source_safe_replay', 'fingerprint_only', 'legacy_redacted')"
    ),
    "ck_ingestion_jobs_payload_partial_replay": (
        "request_payload_partial_replay_eligible = false OR request_payload_replay_eligible = true"
    ),
    "ck_ingestion_jobs_payload_replay_authority": (
        "(request_payload_replay_eligible = true "
        "AND request_payload_representation = 'source_safe_replay' "
        "AND request_payload IS NOT NULL "
        "AND request_payload_fingerprint IS NOT NULL "
        "AND request_payload_replay_expires_at IS NOT NULL) OR "
        "(request_payload_replay_eligible = false "
        "AND request_payload_replay_expires_at IS NULL)"
    ),
    "ck_ingestion_jobs_fingerprint_only_payload_absent": (
        "request_payload_representation <> 'fingerprint_only' OR request_payload IS NULL"
    ),
    "ck_ingestion_jobs_payload_expiry_finite": (
        "request_payload_replay_expires_at IS NULL OR "
        "request_payload_replay_expires_at NOT IN "
        "('infinity'::timestamptz, '-infinity'::timestamptz)"
    ),
    "ck_ingestion_jobs_payload_policy_identity": (
        "btrim(request_payload_policy_version) <> '' AND "
        "btrim(request_payload_retention_authority) <> ''"
    ),
}

_POLICY_COLUMNS = (
    "request_payload_policy_version",
    "request_payload_classification",
    "request_payload_representation",
    "request_payload_replay_eligible",
    "request_payload_partial_replay_eligible",
    "request_payload_replay_expires_at",
    "request_payload_retention_authority",
)

_HISTORICAL_FAILURE_REASON = (
    "Ingestion processing failed. Historical diagnostic evidence was removed during "
    "the source-safe evidence migration."
)


def upgrade() -> None:
    """Add policy snapshots and remove unsupported historical replay payloads."""

    op.add_column(
        "ingestion_jobs",
        sa.Column("request_payload_policy_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("request_payload_classification", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("request_payload_representation", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("request_payload_replay_eligible", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("request_payload_partial_replay_eligible", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("request_payload_replay_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("request_payload_retention_authority", sa.String(length=128), nullable=True),
    )
    # Older SQLAlchemy JSON mappings encoded Python None as the JSON literal null. Normalize
    # absence before classifying historical payloads so JSON null cannot be mistaken for a
    # retained replay body, and apply the same source-safe absence semantics to failure evidence.
    op.execute(
        sa.text(
            """
            UPDATE ingestion_jobs
            SET request_payload = CASE
                    WHEN json_typeof(request_payload) = 'null' THEN NULL
                    ELSE request_payload
                END,
                failure_detail = CASE
                    WHEN json_typeof(failure_detail) = 'null' THEN NULL
                    ELSE failure_detail
                END,
                failure_headers = CASE
                    WHEN json_typeof(failure_headers) = 'null' THEN NULL
                    ELSE failure_headers
                END
            WHERE json_typeof(request_payload) = 'null'
               OR json_typeof(failure_detail) = 'null'
               OR json_typeof(failure_headers) = 'null'
            """
        )
    )
    # Legacy writers could persist raw exception text, request values, and uncontrolled
    # headers. Those values cannot be proven source-safe after the fact. Replace the bounded
    # operator-facing reason and purge the unstructured detail/header bodies before the new
    # projection policy becomes authoritative. Failure codes and failed record keys remain the
    # stable recovery evidence.
    op.execute(
        sa.text(
            """
            UPDATE ingestion_jobs
            SET failure_reason = :historical_failure_reason,
                failure_detail = NULL,
                failure_headers = NULL
            WHERE failure_reason IS NOT NULL
               OR failure_detail IS NOT NULL
               OR failure_headers IS NOT NULL
            """
        ).bindparams(historical_failure_reason=_HISTORICAL_FAILURE_REASON)
    )
    op.execute(
        sa.text(
            """
            UPDATE ingestion_job_failures
            SET failure_reason = :historical_failure_reason
            """
        ).bindparams(historical_failure_reason=_HISTORICAL_FAILURE_REASON)
    )
    # Historical redacted bodies do not carry policy or source authority. Retain them only for
    # the four source-safe internal families, mark every historical row non-replayable, and purge
    # payload bodies that never had a supported replay dispatcher.
    op.execute(
        sa.text(
            """
            UPDATE ingestion_jobs
            SET request_payload = CASE
                    WHEN endpoint IN (
                        '/ingest/instruments',
                        '/ingest/market-prices',
                        '/ingest/fx-rates',
                        '/ingest/business-dates'
                    ) THEN request_payload
                    ELSE NULL
                END,
                request_payload_policy_version = 'ingestion-evidence-policy.legacy.v0',
                request_payload_classification = 'legacy_unclassified',
                request_payload_representation = CASE
                    WHEN endpoint IN (
                        '/ingest/instruments',
                        '/ingest/market-prices',
                        '/ingest/fx-rates',
                        '/ingest/business-dates'
                    ) AND request_payload IS NOT NULL THEN 'legacy_redacted'
                    ELSE 'fingerprint_only'
                END,
                request_payload_replay_eligible = false,
                request_payload_partial_replay_eligible = false,
                request_payload_replay_expires_at = NULL,
                request_payload_retention_authority = 'lotus-core#708'
            """
        )
    )
    for column_name in _POLICY_COLUMNS:
        if column_name == "request_payload_replay_expires_at":
            continue
        op.alter_column("ingestion_jobs", column_name, nullable=False)
    for name, condition in _CHECKS.items():
        op.create_check_constraint(
            name,
            "ingestion_jobs",
            condition,
            postgresql_not_valid=True,
        )
        op.execute(sa.text(f'ALTER TABLE "ingestion_jobs" VALIDATE CONSTRAINT "{name}"'))


def downgrade() -> None:
    """Remove policy columns; purged historical payload bodies cannot be restored."""

    for name in reversed(tuple(_CHECKS)):
        op.drop_constraint(name, "ingestion_jobs", type_="check")
    for column_name in reversed(_POLICY_COLUMNS):
        op.drop_column("ingestion_jobs", column_name)
