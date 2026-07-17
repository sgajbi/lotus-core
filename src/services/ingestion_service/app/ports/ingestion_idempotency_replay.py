"""Application port for non-reserving ingestion idempotency replay lookup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class IngestionIdempotencyReplay:
    """Minimal established-job evidence required to acknowledge a replay."""

    job_id: str
    accepted_count: int


class IngestionIdempotencyReplayReader(Protocol):
    """Read an established same-payload replay without reserving a new key."""

    async def find_matching_job(
        self,
        *,
        endpoint: str,
        idempotency_key: str | None,
        request_payload: dict[str, Any] | None,
    ) -> IngestionIdempotencyReplay | None: ...
