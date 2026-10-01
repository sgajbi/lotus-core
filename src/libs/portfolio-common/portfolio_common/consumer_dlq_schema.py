"""Tenant ownership and access-path schema for consumer DLQ evidence."""

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint


def consumer_dlq_event_table_args(*, observed_at: Any, row_id: Any) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "event_id", name="uq_consumer_dlq_events_tenant_event"),
        CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' AND char_length(tenant_id) <= 128",
            name="ck_consumer_dlq_events_tenant_id_canonical",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "ingestion_job_id"],
            ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"],
            name="fk_consumer_dlq_events_tenant_job",
        ),
        Index(
            "ix_consumer_dlq_events_group_topic_observed_at",
            "tenant_id",
            "consumer_group",
            "original_topic",
            observed_at.desc(),
        ),
        Index("ix_consumer_dlq_events_alternate_lookup_key", "alternate_lookup_key"),
        Index(
            "ix_consumer_dlq_events_job_observed_id",
            "tenant_id",
            "ingestion_job_id",
            observed_at.desc(),
            row_id.desc(),
        ),
    )


def consumer_dlq_replay_audit_table_args(*, requested_at: Any, row_id: Any) -> tuple[Any, ...]:
    return (
        UniqueConstraint(
            "tenant_id", "replay_id", name="uq_consumer_dlq_replay_audit_tenant_replay"
        ),
        CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' AND char_length(tenant_id) <= 128",
            name="ck_consumer_dlq_replay_audit_tenant_id_canonical",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"],
            name="fk_consumer_dlq_replay_audit_tenant_job",
        ),
        Index(
            "ix_consumer_dlq_replay_audit_path_status_requested_at",
            "tenant_id",
            "recovery_path",
            "replay_status",
            requested_at.desc(),
        ),
        Index(
            "ix_consumer_dlq_replay_audit_fingerprint_status_path",
            "tenant_id",
            "replay_fingerprint",
            "replay_status",
            "recovery_path",
            requested_at.desc(),
        ),
        Index("ix_consumer_dlq_replay_audit_alternate_lookup_key", "alternate_lookup_key"),
        Index(
            "ix_consumer_dlq_replay_audit_job_requested_id",
            "tenant_id",
            "job_id",
            requested_at.desc(),
            row_id.desc(),
        ),
    )
