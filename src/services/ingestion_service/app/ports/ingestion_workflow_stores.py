from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from ..DTOs.ingestion_job_dto import IngestionReplayAuditResponse
from ..services.ingestion_job_lifecycle import IngestionJobCreateResult


@dataclass(frozen=True, slots=True)
class ReplayAuditRecord:
    recovery_path: str
    event_id: str
    replay_fingerprint: str
    correlation_id: str | None
    job_id: str | None
    endpoint: str | None
    replay_status: str
    dry_run: bool
    replay_reason: str
    requested_by: str | None
    correlation_missing_reason: str | None = None
    alternate_lookup_key: str | None = None


class IngestionJobStore(Protocol):
    """Store port for job lifecycle creation and idempotency conflict semantics.

    Same endpoint + same idempotency key + same payload returns the existing job with
    ``created=False``. Same endpoint + same idempotency key + different payload raises
    ``IngestionIdempotencyConflictError``.
    """

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
    ) -> IngestionJobCreateResult: ...


class ReplayAuditStore(Protocol):
    """Store port for replay audit records and duplicate replay evidence.

    Implementations must raise the repository's typed audit-write failure when durable
    audit persistence is unavailable. Diagnostic metadata must stay source-safe:
    event identifiers, fingerprints, correlation state, endpoint, status, actor, and
    missing-correlation reason are allowed; raw payloads and secrets are not.
    """

    async def find_successful_replay_audit_by_fingerprint(
        self,
        *,
        replay_fingerprint: str,
        recovery_path: str | None,
    ) -> dict[str, str] | None: ...

    async def record_consumer_dlq_replay_audit(self, record: ReplayAuditRecord) -> str: ...

    async def get_replay_audit(self, *, replay_id: str) -> IngestionReplayAuditResponse | None: ...

    async def list_replay_audits(
        self,
        *,
        limit: int,
        recovery_path: str | None,
        replay_status: str | None,
        replay_fingerprint: str | None,
        job_id: str | None,
    ) -> list[IngestionReplayAuditResponse]: ...


class IngestionAuditDiagnosticsStore(Protocol):
    async def get_idempotency_diagnostics(
        self,
        *,
        lookback_minutes: int,
        limit: int,
    ) -> Any: ...


class ConsumerDlqEventStore(Protocol):
    async def list_consumer_dlq_events(
        self,
        *,
        limit: int,
        original_topic: str | None,
        consumer_group: str | None,
    ) -> list[Any]: ...

    async def get_consumer_dlq_event(self, *, event_id: str) -> Any | None: ...


class OperationalControlStore(Protocol):
    async def get_ops_mode(self) -> Any: ...

    async def update_ops_mode(
        self,
        *,
        mode: str,
        replay_window_start: datetime | None,
        replay_window_end: datetime | None,
        updated_by: str | None,
    ) -> Any: ...
