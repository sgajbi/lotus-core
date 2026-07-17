from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.services.ingestion_service.app.DTOs.ingestion_job_dto import (
    IngestionJobResponse,
)
from src.services.ingestion_service.app.ports.ingestion_workflow_stores import (
    ReplayAuditRecord,
)
from src.services.ingestion_service.app.services.infrastructure_errors import (
    InfrastructureAuditWriteFailed,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    IngestionIdempotencyConflictError,
    IngestionJobCreateResult,
)
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
)

pytestmark = pytest.mark.asyncio


def _job_response(
    *,
    job_id: str,
    endpoint: str = "/ingest/transactions",
    idempotency_key: str | None = "idem-001",
) -> IngestionJobResponse:
    return IngestionJobResponse(
        job_id=job_id,
        endpoint=endpoint,
        entity_type="transaction",
        status="accepted",
        accepted_count=1,
        idempotency_key=idempotency_key,
        correlation_id="corr-001",
        request_id="req-001",
        trace_id="trace-001",
        submitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        retry_count=0,
    )


class _FakeIngestionJobStore:
    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], tuple[dict[str, Any] | None, IngestionJobResponse]] = {}

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
        if not idempotency_key:
            return IngestionJobCreateResult(
                job=_job_response(
                    job_id=job_id,
                    endpoint=endpoint,
                    idempotency_key=idempotency_key,
                ),
                created=True,
            )

        key = (endpoint, idempotency_key)
        existing = self._seen.get(key)
        if existing is not None:
            existing_payload, existing_job = existing
            if existing_payload != request_payload:
                raise IngestionIdempotencyConflictError(
                    endpoint=endpoint,
                    idempotency_key=idempotency_key,
                )
            return IngestionJobCreateResult(job=existing_job, created=False)

        job = _job_response(job_id=job_id, endpoint=endpoint, idempotency_key=idempotency_key)
        self._seen[key] = (request_payload, job)
        return IngestionJobCreateResult(job=job, created=True)


class _FailingReplayAuditStore:
    def __init__(self) -> None:
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
        raise InfrastructureAuditWriteFailed(
            message="Unable to record consumer DLQ replay audit.",
            reason_code="audit_persistence_failed",
        )

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


async def test_create_or_get_job_uses_job_store_idempotency_conflict_semantics() -> None:
    service = IngestionJobService(job_store=_FakeIngestionJobStore())

    created = await service.create_or_get_job(
        job_id="job-001",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        accepted_count=1,
        idempotency_key="idem-001",
        correlation_id="corr-001",
        request_id="req-001",
        trace_id="trace-001",
        request_payload={"transaction_id": "txn-001"},
    )
    duplicate = await service.create_or_get_job(
        job_id="job-002",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        accepted_count=1,
        idempotency_key="idem-001",
        correlation_id="corr-002",
        request_id="req-002",
        trace_id="trace-002",
        request_payload={"transaction_id": "txn-001"},
    )

    assert created.created is True
    assert duplicate.created is False
    assert duplicate.job.job_id == "job-001"

    with pytest.raises(IngestionIdempotencyConflictError):
        await service.create_or_get_job(
            job_id="job-003",
            endpoint="/ingest/transactions",
            entity_type="transaction",
            accepted_count=1,
            idempotency_key="idem-001",
            correlation_id="corr-003",
            request_id="req-003",
            trace_id="trace-003",
            request_payload={"transaction_id": "txn-002"},
        )


async def test_record_replay_audit_uses_store_and_preserves_typed_write_failure() -> None:
    replay_audit_store = _FailingReplayAuditStore()
    service = IngestionJobService(replay_audit_store=replay_audit_store)

    with pytest.raises(InfrastructureAuditWriteFailed) as exc_info:
        await service.record_consumer_dlq_replay_audit(
            recovery_path="consumer_dlq_replay",
            event_id="event-001",
            replay_fingerprint="fp-001",
            correlation_id=None,
            job_id=None,
            endpoint=None,
            replay_status="failed",
            dry_run=False,
            replay_reason="operator replay failed",
            requested_by="ops-token",
            correlation_missing_reason="message_correlation_id_absent",
            alternate_lookup_key="consumer_dlq|topic=transactions.raw.received|event=event-001",
        )

    assert exc_info.value.reason_code == "audit_persistence_failed"
    assert replay_audit_store.records == [
        ReplayAuditRecord(
            recovery_path="consumer_dlq_replay",
            event_id="event-001",
            replay_fingerprint="fp-001",
            correlation_id=None,
            job_id=None,
            endpoint=None,
            replay_status="failed",
            dry_run=False,
            replay_reason="operator replay failed",
            requested_by="ops-token",
            correlation_missing_reason="message_correlation_id_absent",
            alternate_lookup_key="consumer_dlq|topic=transactions.raw.received|event=event-001",
        )
    ]
