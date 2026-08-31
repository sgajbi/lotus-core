"""Application port for non-reserving ingestion idempotency replay lookup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class IngestionIdempotencyReplay:
    """Established-job lifecycle evidence required to resolve a replay."""

    job_id: str
    accepted_count: int
    status: str
    failure_reason: str | None
    failure_status_code: int | None
    failure_code: str | None
    failure_detail: dict[str, Any] | None
    failure_headers: dict[str, str] | None


class IngestionIdempotencyReplayReader(Protocol):
    """Read an established same-payload replay without reserving a new key."""

    async def find_matching_job(
        self,
        *,
        tenant_id: str,
        endpoint: str,
        idempotency_key: str | None,
        request_payload: dict[str, Any] | None,
    ) -> IngestionIdempotencyReplay | None: ...
