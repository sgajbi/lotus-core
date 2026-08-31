"""PostgreSQL proof that consumer DLQ evidence is visible only to its owning tenant."""

from __future__ import annotations

import pytest
from portfolio_common.database_models import ConsumerDlqEvent, ConsumerDlqReplayAudit, IngestionJob
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.services.ingestion_consumer_dlq_events import (
    get_consumer_dlq_event_response,
    list_consumer_dlq_event_responses,
)
from src.services.ingestion_service.app.services.ingestion_replay_audits import (
    find_successful_replay_audit_by_fingerprint_response,
    get_replay_audit_response,
    list_replay_audit_responses,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]


def _job(*, job_id: str, tenant_id: str) -> IngestionJob:
    return IngestionJob(
        job_id=job_id,
        tenant_id=tenant_id,
        endpoint="/ingest/transactions",
        entity_type="transaction",
        status="queued",
        accepted_count=1,
        correlation_id=f"corr-{job_id}",
        request_id=f"request-{job_id}",
        trace_id=f"trace-{job_id}",
        request_payload=None,
        request_payload_fingerprint=None,
        request_payload_policy_version="test-v1",
        request_payload_classification="internal",
        request_payload_representation="fingerprint_only",
        request_payload_replay_eligible=False,
        request_payload_partial_replay_eligible=False,
        request_payload_replay_expires_at=None,
        request_payload_retention_authority="test-policy",
    )


def _event(*, event_id: str, job_id: str | None) -> ConsumerDlqEvent:
    return ConsumerDlqEvent(
        event_id=event_id,
        original_topic="transactions.raw.received",
        consumer_group="persistence-service-group",
        dlq_topic="dlq.persistence_service",
        original_key=f"key-{event_id}",
        error_reason_code="VALIDATION_ERROR",
        error_reason="Source record failed governed validation.",
        correlation_id=f"corr-{job_id}" if job_id else None,
        ingestion_job_id=job_id,
        payload_excerpt='{"source_record":"redacted"}',
    )


async def test_consumer_dlq_queries_hide_foreign_and_unattributable_evidence(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _job(job_id="job-tenant-a", tenant_id="tenant-a"),
            _job(job_id="job-tenant-b", tenant_id="tenant-b"),
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            _event(event_id="dlq-tenant-a", job_id="job-tenant-a"),
            _event(event_id="dlq-tenant-b", job_id="job-tenant-b"),
            _event(event_id="dlq-unattributable", job_id=None),
        ]
    )
    await async_db_session.flush()

    async def session_factory():
        yield async_db_session

    visible = await list_consumer_dlq_event_responses(
        tenant_id="tenant-a",
        limit=100,
        original_topic=None,
        consumer_group=None,
        session_factory=session_factory,
    )

    assert [event.event_id for event in visible] == ["dlq-tenant-a"]
    assert (
        await get_consumer_dlq_event_response(
            tenant_id="tenant-a",
            event_id="dlq-tenant-b",
            session_factory=session_factory,
        )
        is None
    )
    assert (
        await get_consumer_dlq_event_response(
            tenant_id="tenant-a",
            event_id="dlq-unattributable",
            session_factory=session_factory,
        )
        is None
    )


async def test_replay_audit_queries_and_duplicate_detection_are_tenant_scoped(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _job(job_id="job-audit-a", tenant_id="tenant-a"),
            _job(job_id="job-audit-b", tenant_id="tenant-b"),
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            _replay_audit(replay_id="replay-a", job_id="job-audit-a"),
            _replay_audit(replay_id="replay-b", job_id="job-audit-b"),
            _replay_audit(replay_id="replay-unattributable", job_id=None),
        ]
    )
    await async_db_session.flush()

    async def session_factory():
        yield async_db_session

    visible = await list_replay_audit_responses(
        tenant_id="tenant-a",
        limit=100,
        recovery_path=None,
        replay_status=None,
        replay_fingerprint=None,
        job_id=None,
        session_factory=session_factory,
    )

    assert [audit.replay_id for audit in visible] == ["replay-a"]
    assert (
        await get_replay_audit_response(
            tenant_id="tenant-a",
            replay_id="replay-b",
            session_factory=session_factory,
        )
        is None
    )
    assert await find_successful_replay_audit_by_fingerprint_response(
        tenant_id="tenant-a",
        replay_fingerprint="shared-fingerprint",
        recovery_path="consumer_dlq_replay",
        session_factory=session_factory,
    ) == {"replay_id": "replay-a", "replay_status": "replayed"}


def _replay_audit(*, replay_id: str, job_id: str | None) -> ConsumerDlqReplayAudit:
    return ConsumerDlqReplayAudit(
        replay_id=replay_id,
        recovery_path="consumer_dlq_replay",
        event_id=f"event-{replay_id}",
        replay_fingerprint="shared-fingerprint",
        correlation_id=f"correlation-{replay_id}",
        job_id=job_id,
        endpoint="/ingest/transactions",
        replay_status="replayed",
        dry_run=False,
        replay_reason="Governed replay completed.",
        requested_by="test-operator",
    )
