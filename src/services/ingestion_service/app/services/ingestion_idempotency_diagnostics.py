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
        endpoint_payload_counts = (
            select(
                DBIngestionJob.idempotency_key.label("idempotency_key"),
                DBIngestionJob.endpoint.label("endpoint"),
                func.count(func.distinct(DBIngestionJob.request_payload_fingerprint)).label(
                    "payload_fingerprint_count"
                ),
            )
            .where(
                and_(
                    DBIngestionJob.submitted_at >= since,
                    DBIngestionJob.idempotency_key.is_not(None),
                )
            )
            .group_by(DBIngestionJob.idempotency_key, DBIngestionJob.endpoint)
            .subquery()
        )
        rows = await db.execute(
            select(
                DBIngestionJob.idempotency_key,
                func.count(func.distinct(DBIngestionJob.id)).label("usage_count"),
                func.count(func.distinct(DBIngestionJob.endpoint)).label("endpoint_count"),
                func.count(func.distinct(DBIngestionJob.request_payload_fingerprint)).label(
                    "payload_fingerprint_count"
                ),
                func.coalesce(
                    func.max(endpoint_payload_counts.c.payload_fingerprint_count), 0
                ).label("max_payload_fingerprints_per_endpoint"),
                func.array_agg(func.distinct(DBIngestionJob.endpoint)).label("endpoints"),
                func.min(DBIngestionJob.submitted_at).label("first_seen_at"),
                func.max(DBIngestionJob.submitted_at).label("last_seen_at"),
            )
            .outerjoin(
                endpoint_payload_counts,
                endpoint_payload_counts.c.idempotency_key == DBIngestionJob.idempotency_key,
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
                payload_fingerprint_count_raw=payload_fingerprint_count_raw,
                max_payload_fingerprints_per_endpoint_raw=(
                    max_payload_fingerprints_per_endpoint_raw
                ),
                endpoints_raw=endpoints_raw,
                first_seen_at=first_seen_at,
                last_seen_at=last_seen_at,
            )
            for (
                key,
                usage_count_raw,
                endpoint_count_raw,
                payload_fingerprint_count_raw,
                max_payload_fingerprints_per_endpoint_raw,
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
    payload_fingerprint_count_raw: object,
    max_payload_fingerprints_per_endpoint_raw: object,
    endpoints_raw: object,
    first_seen_at,
    last_seen_at,
) -> IngestionIdempotencyDiagnosticItemResponse:
    usage_count = int(usage_count_raw or 0)
    endpoint_count = int(endpoint_count_raw or 0)
    payload_fingerprint_count = int(payload_fingerprint_count_raw or 0)
    max_payload_fingerprints_per_endpoint = int(max_payload_fingerprints_per_endpoint_raw or 0)
    endpoints = sorted(list(endpoints_raw or []))
    payload_conflict_detected = max_payload_fingerprints_per_endpoint > 1
    collision_detected = endpoint_count > 1 or payload_conflict_detected
    return IngestionIdempotencyDiagnosticItemResponse(
        idempotency_key=key,
        usage_count=usage_count,
        endpoint_count=endpoint_count,
        payload_fingerprint_count=payload_fingerprint_count,
        max_payload_fingerprints_per_endpoint=max_payload_fingerprints_per_endpoint,
        endpoints=endpoints,
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        collision_detected=collision_detected,
        payload_conflict_detected=payload_conflict_detected,
        reuse_classification=_classify_idempotency_reuse(
            endpoint_count=endpoint_count,
            payload_conflict_detected=payload_conflict_detected,
        ),
    )


def _classify_idempotency_reuse(
    *,
    endpoint_count: int,
    payload_conflict_detected: bool,
) -> str:
    if payload_conflict_detected:
        return "conflicting_payload_reuse"
    if endpoint_count > 1:
        return "cross_endpoint_reuse"
    return "single_record_or_benign_replay"
