"""Framework-neutral authority for the existing source-confirmation operation owner."""

from dataclasses import dataclass
from typing import Protocol

from portfolio_common.domain.tenant import TenantContext


@dataclass(frozen=True, slots=True)
class SourceOperationJob:
    job_id: str
    status: str
    idempotency_key_reference: str | None


@dataclass(frozen=True, slots=True)
class SourceOperationCreation:
    job: SourceOperationJob
    created: bool


class SourceCorrectionOperationOwner(Protocol):
    async def assert_ingestion_writable(self) -> None: ...

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
        tenant_context: TenantContext,
        request_payload: dict[str, object] | None,
    ) -> SourceOperationCreation: ...
