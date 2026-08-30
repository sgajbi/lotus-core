"""SQLAlchemy adapter for established ingestion idempotency replays."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ports.ingestion_idempotency_replay import IngestionIdempotencyReplay
from ..services.ingestion_payload_evidence import ingestion_payload_fingerprint_matches


class SqlAlchemyIngestionIdempotencyReplayReader:
    """Return only established jobs whose endpoint, key, and payload all match."""

    def __init__(self, db: AsyncSession, *, fingerprint_keyring: Mapping[str, str]) -> None:
        self._db = db
        self._fingerprint_keyring = dict(fingerprint_keyring)

    async def find_matching_job(
        self,
        *,
        tenant_id: str,
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
                    DBIngestionJob.tenant_id == tenant_id,
                    DBIngestionJob.endpoint == endpoint,
                    DBIngestionJob.idempotency_key == idempotency_key,
                )
            )
            .order_by(desc(DBIngestionJob.submitted_at))
            .limit(1)
        )
        if existing is None or not _payload_matches(
            existing,
            request_payload,
            fingerprint_keyring=self._fingerprint_keyring,
        ):
            return None
        return IngestionIdempotencyReplay(
            job_id=str(existing.job_id),
            accepted_count=int(existing.accepted_count),
            status=str(existing.status),
            failure_reason=existing.failure_reason,
            failure_status_code=existing.failure_status_code,
            failure_code=existing.failure_code,
            failure_detail=existing.failure_detail,
            failure_headers=existing.failure_headers,
        )


def _payload_matches(
    existing: Any,
    requested_payload: dict[str, Any] | None,
    *,
    fingerprint_keyring: Mapping[str, str],
) -> bool:
    existing_fingerprint = getattr(existing, "request_payload_fingerprint", None)
    if existing_fingerprint is None:
        return False
    return ingestion_payload_fingerprint_matches(
        stored_fingerprint=existing_fingerprint,
        payload=requested_payload,
        secrets_by_key_id=fingerprint_keyring,
    )
