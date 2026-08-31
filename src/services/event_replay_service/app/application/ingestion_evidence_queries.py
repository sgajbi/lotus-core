from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

from portfolio_common.domain.tenant import TenantContext

from ..proof_builders.ingestion_evidence_bundle import IngestionEvidenceBundleBuilder
from .ingestion_operations_queries import IngestionOperationsNotFound

_EVIDENCE_LIMIT = 500
_EVIDENCE_FETCH_LIMIT = _EVIDENCE_LIMIT + 1


class IngestionEvidenceReader(Protocol):
    async def get_job(self, job_id: str, *, tenant_id: str) -> Any: ...

    async def list_failures(self, *, job_id: str, limit: int) -> list[Any]: ...

    async def list_replay_audits(
        self,
        *,
        job_id: str,
        limit: int,
        recovery_path: str | None,
        replay_status: str | None,
        replay_fingerprint: str | None,
    ) -> list[Any]: ...

    async def list_consumer_dlq_events_by_job_id(
        self,
        job_id: str,
        *,
        limit: int,
    ) -> list[Any]: ...

    async def list_consumer_dlq_events_by_event_ids(
        self,
        event_ids: tuple[str, ...],
        *,
        limit: int,
    ) -> list[Any]: ...

    async def get_job_replay_context(self, job_id: str, *, tenant_id: str) -> Any: ...


@dataclass(frozen=True)
class IngestionEvidenceQueryService:
    ingestion_job_service: IngestionEvidenceReader
    bundle_builder: IngestionEvidenceBundleBuilder = field(
        default_factory=IngestionEvidenceBundleBuilder
    )

    async def get_evidence_bundle(self, job_id: str, *, tenant_context: TenantContext) -> Any:
        tenant_id = tenant_context.tenant_id_text
        job = await self.ingestion_job_service.get_job(job_id, tenant_id=tenant_id)
        if job is None:
            raise IngestionOperationsNotFound(
                code="INGESTION_JOB_NOT_FOUND",
                message=f"Ingestion job '{job_id}' was not found.",
            )
        failures, replay_audits, consumer_dlq_events, replay_context = await asyncio.gather(
            self.ingestion_job_service.list_failures(
                job_id=job_id,
                limit=_EVIDENCE_FETCH_LIMIT,
            ),
            self.ingestion_job_service.list_replay_audits(
                job_id=job_id,
                limit=_EVIDENCE_FETCH_LIMIT,
                recovery_path=None,
                replay_status=None,
                replay_fingerprint=None,
            ),
            self.ingestion_job_service.list_consumer_dlq_events_by_job_id(
                job_id,
                limit=_EVIDENCE_FETCH_LIMIT,
            ),
            self.ingestion_job_service.get_job_replay_context(job_id, tenant_id=tenant_id),
        )
        replay_event_ids = tuple(sorted({audit.event_id for audit in replay_audits}))
        replay_correlated_dlq_events = (
            await self.ingestion_job_service.list_consumer_dlq_events_by_event_ids(
                replay_event_ids,
                limit=_EVIDENCE_FETCH_LIMIT,
            )
            if replay_event_ids
            else []
        )
        replay_correlated_dlq_events = [
            event
            for event in replay_correlated_dlq_events
            if getattr(event, "ingestion_job_id", None) in {None, job_id}
        ]
        merged_dlq_events = _merge_consumer_dlq_events(
            consumer_dlq_events,
            replay_correlated_dlq_events,
            job_id=job_id,
        )
        request_payload = replay_context.request_payload if replay_context is not None else None
        evidence_complete = all(
            len(evidence_rows) <= _EVIDENCE_LIMIT
            for evidence_rows in (
                failures,
                replay_audits,
                consumer_dlq_events,
                replay_correlated_dlq_events,
                merged_dlq_events,
            )
        )
        return self.bundle_builder.build(
            job=job,
            failures=failures[:_EVIDENCE_LIMIT],
            replay_audits=replay_audits[:_EVIDENCE_LIMIT],
            consumer_dlq_events=merged_dlq_events[:_EVIDENCE_LIMIT],
            request_payload=request_payload,
            evidence_complete=evidence_complete,
        )

    def _build_bundle(self, **kwargs: Any) -> Any:
        """Compatibility seam for focused builder tests; runtime callers use get_evidence_bundle."""
        return self.bundle_builder.build(**kwargs)


def _merge_consumer_dlq_events(
    *event_groups: list[Any],
    job_id: str,
) -> list[Any]:
    by_event_id = {
        event.event_id: event
        for event_group in event_groups
        for event in event_group
        if getattr(event, "ingestion_job_id", None) in {None, job_id}
    }
    return sorted(
        by_event_id.values(),
        key=lambda event: (event.observed_at, event.event_id),
        reverse=True,
    )
