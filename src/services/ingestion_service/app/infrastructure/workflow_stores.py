from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..ports.ingestion_workflow_stores import ReplayAuditRecord
from ..services.ingestion_job_lifecycle import (
    IngestionJobCreateResult,
    create_or_get_job_result,
)
from ..services.ingestion_replay_audits import (
    find_successful_replay_audit_by_fingerprint_response,
    get_replay_audit_response,
    list_replay_audit_responses,
    record_consumer_dlq_replay_audit_response,
)


class SqlAlchemyIngestionJobStore:
    def __init__(self, *, session_factory: Callable[[], Any]):
        self._session_factory = session_factory

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
        return await create_or_get_job_result(
            job_id=job_id,
            endpoint=endpoint,
            entity_type=entity_type,
            accepted_count=accepted_count,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_id=request_id,
            trace_id=trace_id,
            request_payload=request_payload,
            session_factory=self._session_factory,
        )


class SqlAlchemyReplayAuditStore:
    def __init__(self, *, session_factory: Callable[[], Any]):
        self._session_factory = session_factory

    async def find_successful_replay_audit_by_fingerprint(
        self,
        *,
        replay_fingerprint: str,
        recovery_path: str | None,
    ) -> dict[str, str] | None:
        return await find_successful_replay_audit_by_fingerprint_response(
            replay_fingerprint=replay_fingerprint,
            recovery_path=recovery_path,
            session_factory=self._session_factory,
        )

    async def record_consumer_dlq_replay_audit(self, record: ReplayAuditRecord) -> str:
        return await record_consumer_dlq_replay_audit_response(
            recovery_path=record.recovery_path,
            event_id=record.event_id,
            replay_fingerprint=record.replay_fingerprint,
            correlation_id=record.correlation_id,
            correlation_missing_reason=record.correlation_missing_reason,
            alternate_lookup_key=record.alternate_lookup_key,
            job_id=record.job_id,
            endpoint=record.endpoint,
            replay_status=record.replay_status,
            dry_run=record.dry_run,
            replay_reason=record.replay_reason,
            requested_by=record.requested_by,
            session_factory=self._session_factory,
        )

    async def get_replay_audit(self, *, replay_id: str):
        return await get_replay_audit_response(
            replay_id=replay_id,
            session_factory=self._session_factory,
        )

    async def list_replay_audits(
        self,
        *,
        limit: int,
        recovery_path: str | None,
        replay_status: str | None,
        replay_fingerprint: str | None,
        job_id: str | None,
    ):
        return await list_replay_audit_responses(
            limit=limit,
            recovery_path=recovery_path,
            replay_status=replay_status,
            replay_fingerprint=replay_fingerprint,
            job_id=job_id,
            session_factory=self._session_factory,
        )
