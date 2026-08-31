"""Database constraints and indexes owned by the ingestion-job aggregate."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index

from .database_text_contract import CANONICAL_TENANT_ID_CHECK_SQL


def ingestion_job_table_args(*, submitted_at: Any, row_id: Any) -> tuple[Any, ...]:
    """Return the governed ingestion-job integrity and access-path contract."""

    return (
        CheckConstraint(
            f"{CANONICAL_TENANT_ID_CHECK_SQL} AND char_length(tenant_id) <= 128",
            name="ck_ingestion_jobs_tenant_authority",
        ),
        CheckConstraint(
            "(failure_status_code IS NULL AND failure_code IS NULL "
            "AND failure_detail IS NULL AND failure_headers IS NULL) OR "
            "(failure_status_code IS NOT NULL "
            "AND failure_status_code BETWEEN 400 AND 599 "
            "AND failure_code IS NOT NULL "
            "AND failure_code = btrim(failure_code) "
            "AND failure_code <> '')",
            name="ck_ingestion_jobs_failure_outcome_complete",
        ),
        CheckConstraint(
            "request_payload_fingerprint IS NULL OR "
            "request_payload_fingerprint ~ "
            "'^hmac-sha256:v1:[A-Za-z0-9][A-Za-z0-9._-]{0,63}:[0-9a-f]{64}$'",
            name="ck_ingestion_jobs_payload_fingerprint_format",
        ),
        CheckConstraint(
            "request_payload_classification IN ('internal', 'confidential', 'restricted', "
            "'legacy_unclassified')",
            name="ck_ingestion_jobs_payload_classification",
        ),
        CheckConstraint(
            "request_payload_representation IN ('source_safe_replay', 'fingerprint_only', "
            "'legacy_redacted')",
            name="ck_ingestion_jobs_payload_representation",
        ),
        CheckConstraint(
            "request_payload_partial_replay_eligible = false OR "
            "request_payload_replay_eligible = true",
            name="ck_ingestion_jobs_payload_partial_replay",
        ),
        CheckConstraint(
            "(request_payload_replay_eligible = true "
            "AND request_payload_representation = 'source_safe_replay' "
            "AND request_payload IS NOT NULL "
            "AND request_payload_fingerprint IS NOT NULL "
            "AND request_payload_replay_expires_at IS NOT NULL) OR "
            "(request_payload_replay_eligible = false "
            "AND request_payload_replay_expires_at IS NULL)",
            name="ck_ingestion_jobs_payload_replay_authority",
        ),
        CheckConstraint(
            "request_payload_representation <> 'fingerprint_only' OR request_payload IS NULL",
            name="ck_ingestion_jobs_fingerprint_only_payload_absent",
        ),
        CheckConstraint(
            "request_payload_replay_expires_at IS NULL OR "
            "request_payload_replay_expires_at NOT IN "
            "('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ingestion_jobs_payload_expiry_finite",
        ),
        CheckConstraint(
            "btrim(request_payload_policy_version) <> '' AND "
            "btrim(request_payload_retention_authority) <> ''",
            name="ck_ingestion_jobs_payload_policy_identity",
        ),
        Index("ix_ingestion_jobs_submitted_at", "submitted_at"),
        Index("ix_ingestion_jobs_tenant_submitted_at", "tenant_id", submitted_at.desc()),
        Index(
            "ix_ingestion_jobs_tenant_endpoint_idempotency_submitted",
            "tenant_id",
            "endpoint",
            "idempotency_key",
            submitted_at.desc(),
        ),
        Index("ix_ingestion_jobs_status_submitted_at", "status", submitted_at.desc()),
        Index(
            "ix_ingestion_jobs_idempotency_key_submitted_at",
            "idempotency_key",
            submitted_at.desc(),
        ),
        Index(
            "ix_ingestion_jobs_idempotency_payload_fingerprint",
            "idempotency_key",
            "request_payload_fingerprint",
        ),
        Index(
            "ix_ingestion_jobs_submitted_completed_at",
            "submitted_at",
            "completed_at",
        ),
        Index(
            "ix_ingestion_jobs_correlation_status_id",
            "correlation_id",
            "status",
            row_id.desc(),
        ),
    )
