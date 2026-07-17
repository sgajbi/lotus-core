"""Application port for non-reserving ingestion idempotency replay lookup."""

from __future__ import annotations

from typing import Any, Protocol

from ..DTOs.ingestion_job_dto import IngestionJobResponse


class IngestionIdempotencyReplayReader(Protocol):
    """Read an established same-payload replay without reserving a new key."""

    async def find_matching_job(
        self,
        *,
        endpoint: str,
        idempotency_key: str | None,
        request_payload: dict[str, Any] | None,
    ) -> IngestionJobResponse | None: ...
