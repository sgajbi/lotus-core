from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.services.ingestion_service.app.DTOs.ingestion_job_dto import IngestionJobResponse
from src.services.ingestion_service.app.application.workflow_policies import (
    ApplicationCommandEnvelope,
    AuditWorkflow,
    CorrelationContext,
    IdempotencyWorkflow,
)
from src.services.ingestion_service.app.ports.ingestion_workflow_stores import ReplayAuditRecord
from src.services.ingestion_service.app.services.infrastructure_errors import (
    InfrastructureAuditWriteFailed,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    IngestionIdempotencyConflictError,
    IngestionJobCreateResult,
)

pytestmark = pytest.mark.asyncio


def _command(*, payload: dict[str, Any]) -> ApplicationCommandEnvelope:
    return ApplicationCommandEnvelope(
        command_id="job-001",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        accepted_count=1,
        idempotency_key="idem-001",
        correlation=CorrelationContext(
            correlation_id="corr-001",
            request_id="req-001",
            trace_id="trace-001",
            causation_id="causation-001",
            source_lineage={"source_system": "unit"},
        ),
        request_payload=payload,
    )


def _job_response(*, job_id: str) -> IngestionJobResponse:
    return IngestionJobResponse(
        job_id=job_id,
        endpoint="/ingest/transactions",
        entity_type="transaction",
        status="accepted",
        accepted_count=1,
        idempotency_key="idem-001",
        correlation_id="corr-001",
        request_id="req-001",
        trace_id="trace-001",
        submitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        retry_count=0,
    )


class _FakeIdempotencyStore:
    def __init__(self) -> None:
        self.seen_payload: dict[str, Any] | None = None
        self.created_job = _job_response(job_id="job-001")

    async def create_or_get_job(
        self,
        *,
        job_id: str,
        endpoint: str,
        entity_type: str,
        accepted_count: int,
        idempotency_key: str | None,
        correlation_id: str,
        request_id: str,
        trace_id: str,
        request_payload: dict[str, Any] | None,
    ) -> IngestionJobCreateResult:
        if self.seen_payload is None:
            self.seen_payload = request_payload
            return IngestionJobCreateResult(job=self.created_job, created=True)
        if self.seen_payload != request_payload:
            raise IngestionIdempotencyConflictError(
                endpoint=endpoint,
                idempotency_key=idempotency_key or "",
            )
        return IngestionJobCreateResult(job=self.created_job, created=False)


class _FakeReplayAuditStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.records: list[ReplayAuditRecord] = []

    async def find_successful_replay_audit_by_fingerprint(
        self,
        *,
        replay_fingerprint: str,
        recovery_path: str | None,
    ) -> dict[str, str] | None:
        return None

    async def record_consumer_dlq_replay_audit(self, record: ReplayAuditRecord) -> str:
        self.records.append(record)
        if self.fail:
            raise InfrastructureAuditWriteFailed(
                message="Unable to record consumer DLQ replay audit.",
                reason_code="audit_persistence_failed",
            )
        return "replay-001"

    async def get_replay_audit(self, *, replay_id: str):
        return None

    async def list_replay_audits(
        self,
        *,
        limit: int,
        recovery_path: str | None,
        replay_status: str | None,
        replay_fingerprint: str | None,
        job_id: str | None,
    ):
        return []


async def test_idempotency_workflow_returns_existing_job_for_duplicate_payload() -> None:
    workflow = IdempotencyWorkflow(_FakeIdempotencyStore())

    created = await workflow.create_or_get(_command(payload={"transaction_id": "txn-001"}))
    duplicate = await workflow.create_or_get(_command(payload={"transaction_id": "txn-001"}))

    assert created.created is True
    assert duplicate.created is False
    assert duplicate.job.job_id == "job-001"


async def test_idempotency_workflow_preserves_conflict_outcome() -> None:
    workflow = IdempotencyWorkflow(_FakeIdempotencyStore())

    await workflow.create_or_get(_command(payload={"transaction_id": "txn-001"}))

    with pytest.raises(IngestionIdempotencyConflictError):
        await workflow.create_or_get(_command(payload={"transaction_id": "txn-002"}))


async def test_audit_workflow_records_replay_audit_through_port() -> None:
    store = _FakeReplayAuditStore()
    workflow = AuditWorkflow(store)
    record = ReplayAuditRecord(
        recovery_path="consumer_dlq_replay",
        event_id="event-001",
        replay_fingerprint="fp-001",
        correlation_id="corr-001",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
        job_id="job-001",
        endpoint="/ingest/transactions",
        replay_status="succeeded",
        dry_run=False,
        replay_reason="operator replay",
        requested_by="ops-token",
    )

    replay_id = await workflow.record_replay_audit(record)

    assert replay_id == "replay-001"
    assert store.records == [record]


async def test_audit_workflow_preserves_fail_closed_audit_error() -> None:
    store = _FakeReplayAuditStore(fail=True)
    workflow = AuditWorkflow(store)
    record = ReplayAuditRecord(
        recovery_path="consumer_dlq_replay",
        event_id="event-001",
        replay_fingerprint="fp-001",
        correlation_id=None,
        correlation_missing_reason="message_correlation_id_absent",
        alternate_lookup_key="consumer_dlq|topic=transactions.raw.received|event=event-001",
        job_id=None,
        endpoint=None,
        replay_status="failed",
        dry_run=False,
        replay_reason="operator replay failed",
        requested_by="ops-token",
    )

    with pytest.raises(InfrastructureAuditWriteFailed):
        await workflow.record_replay_audit(record)

    assert store.records == [record]
