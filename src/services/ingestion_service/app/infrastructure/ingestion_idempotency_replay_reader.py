"""SQLAlchemy adapter for established ingestion idempotency replays."""

from __future__ import annotations

from typing import Any

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ports.ingestion_idempotency_replay import IngestionIdempotencyReplay
from ..services.ingestion_payload_evidence import (
    ingestion_payload_fingerprint,
    source_safe_payload_fingerprint,
)


class SqlAlchemyIngestionIdempotencyReplayReader:
    """Return only established jobs whose endpoint, key, and payload all match."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def find_matching_job(
        self,
        *,
        endpoint: str,
        idempotency_key: str | None,
        request_payload: dict[str, Any] | None,
    ) -> IngestionIdempotencyReplay | None:
        if not idempotency_key:
            return None

        existing = await self._db.scalar(
            select(DBIngestionJob)
            .where(
                and_(
                    DBIngestionJob.endpoint == endpoint,
                    DBIngestionJob.idempotency_key == idempotency_key,
                )
            )
            .order_by(desc(DBIngestionJob.submitted_at))
            .limit(1)
        )
        if existing is None or not _payload_matches(existing, request_payload):
            return None
        return IngestionIdempotencyReplay(
            job_id=str(existing.job_id),
            accepted_count=int(existing.accepted_count),
        )


def _payload_matches(existing: Any, requested_payload: dict[str, Any] | None) -> bool:
    existing_fingerprint = getattr(existing, "request_payload_fingerprint", None)
    if existing_fingerprint is not None:
        return existing_fingerprint == ingestion_payload_fingerprint(requested_payload)
    existing_payload = (
        existing.request_payload if isinstance(existing.request_payload, dict) else None
    )
    return source_safe_payload_fingerprint(existing_payload) == source_safe_payload_fingerprint(
        requested_payload
    )
