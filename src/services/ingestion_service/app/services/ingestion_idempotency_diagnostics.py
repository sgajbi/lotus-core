from __future__ import annotations

from datetime import UTC, datetime, timedelta

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import and_, desc, func, select

from ..DTOs.ingestion_job_dto import (
    IngestionIdempotencyDiagnosticItemResponse,
    IngestionIdempotencyDiagnosticsResponse,
)


async def load_idempotency_diagnostics_response(
    *,
    lookback_minutes: int,
    limit: int,
    session_factory,
) -> IngestionIdempotencyDiagnosticsResponse:
    async for db in session_factory():
        since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
        rows = await db.execute(
            select(
                DBIngestionJob.idempotency_key,
                func.count(DBIngestionJob.id).label("usage_count"),
                func.count(func.distinct(DBIngestionJob.endpoint)).label("endpoint_count"),
                func.array_agg(func.distinct(DBIngestionJob.endpoint)).label("endpoints"),
                func.min(DBIngestionJob.submitted_at).label("first_seen_at"),
                func.max(DBIngestionJob.submitted_at).label("last_seen_at"),
            )
            .where(
                and_(
                    DBIngestionJob.submitted_at >= since,
                    DBIngestionJob.idempotency_key.is_not(None),
                )
            )
            .group_by(DBIngestionJob.idempotency_key)
            .order_by(desc("usage_count"))
            .limit(limit)
        )
        items = [
            _to_idempotency_diagnostic_item(
                key=key,
                usage_count_raw=usage_count_raw,
                endpoint_count_raw=endpoint_count_raw,
                endpoints_raw=endpoints_raw,
                first_seen_at=first_seen_at,
                last_seen_at=last_seen_at,
            )
            for (
                key,
                usage_count_raw,
                endpoint_count_raw,
                endpoints_raw,
                first_seen_at,
                last_seen_at,
            ) in rows
        ]
        return IngestionIdempotencyDiagnosticsResponse(
            lookback_minutes=lookback_minutes,
            total_keys=len(items),
            collisions=sum(1 for item in items if item.collision_detected),
            keys=items,
        )
    return IngestionIdempotencyDiagnosticsResponse(
        lookback_minutes=lookback_minutes,
        total_keys=0,
        collisions=0,
        keys=[],
    )


def _to_idempotency_diagnostic_item(
    *,
    key: str,
    usage_count_raw: object,
    endpoint_count_raw: object,
    endpoints_raw: object,
    first_seen_at,
    last_seen_at,
) -> IngestionIdempotencyDiagnosticItemResponse:
    usage_count = int(usage_count_raw or 0)
    endpoint_count = int(endpoint_count_raw or 0)
    endpoints = sorted(list(endpoints_raw or []))
    return IngestionIdempotencyDiagnosticItemResponse(
        idempotency_key=key,
        usage_count=usage_count,
        endpoint_count=endpoint_count,
        endpoints=endpoints,
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        collision_detected=endpoint_count > 1,
    )
