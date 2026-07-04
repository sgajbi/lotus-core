from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..ports.ingestion_workflow_stores import (
    IngestionJobStore,
    ReplayAuditRecord,
    ReplayAuditStore,
)
from ..services.ingestion_job_lifecycle import IngestionJobCreateResult


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    correlation_id: str
    request_id: str
    trace_id: str
    causation_id: str | None = None
    source_lineage: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ApplicationCommandEnvelope:
    command_id: str
    endpoint: str
    entity_type: str
    accepted_count: int
    idempotency_key: str | None
    correlation: CorrelationContext
    request_payload: dict[str, Any] | None


class IdempotencyWorkflow:
    def __init__(self, store: IngestionJobStore):
        self._store = store

    async def create_or_get(self, command: ApplicationCommandEnvelope) -> IngestionJobCreateResult:
        return await self._store.create_or_get_job(
            job_id=command.command_id,
            endpoint=command.endpoint,
            entity_type=command.entity_type,
            accepted_count=command.accepted_count,
            idempotency_key=command.idempotency_key,
            correlation_id=command.correlation.correlation_id,
            request_id=command.correlation.request_id,
            trace_id=command.correlation.trace_id,
            request_payload=command.request_payload,
        )


class AuditWorkflow:
    def __init__(self, replay_audit_store: ReplayAuditStore):
        self._replay_audit_store = replay_audit_store

    async def record_replay_audit(self, record: ReplayAuditRecord) -> str:
        return await self._replay_audit_store.record_consumer_dlq_replay_audit(record)
