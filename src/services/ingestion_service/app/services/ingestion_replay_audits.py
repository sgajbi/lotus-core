from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from portfolio_common.database_models import ConsumerDlqReplayAudit as DBConsumerDlqReplayAudit
from portfolio_common.monitoring import (
    INGESTION_REPLAY_AUDIT_TOTAL,
    INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL,
    INGESTION_REPLAY_FAILURE_TOTAL,
)
from sqlalchemy import and_, desc, select

from ..DTOs.ingestion_job_dto import IngestionReplayAuditResponse

_SUCCESSFUL_REPLAY_AUDIT_STATUSES = {"replayed", "replayed_bookkeeping_failed"}
_FAILED_REPLAY_AUDIT_STATUSES = {"not_replayable", "failed", "replayed_bookkeeping_failed"}


def to_replay_audit_response(row: DBConsumerDlqReplayAudit) -> IngestionReplayAuditResponse:
    return IngestionReplayAuditResponse(
        replay_id=row.replay_id,
        recovery_path=row.recovery_path,  # type: ignore[arg-type]
        event_id=row.event_id,
        replay_fingerprint=row.replay_fingerprint,
        correlation_id=row.correlation_id,
        job_id=row.job_id,
        endpoint=row.endpoint,
        replay_status=row.replay_status,  # type: ignore[arg-type]
        dry_run=bool(row.dry_run),
        replay_reason=row.replay_reason,
        requested_by=row.requested_by,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
    )


async def list_replay_audit_responses(
    *,
    limit: int,
    recovery_path: str | None,
    replay_status: str | None,
    replay_fingerprint: str | None,
    job_id: str | None,
    session_factory,
) -> list[IngestionReplayAuditResponse]:
    async for db in session_factory():
        stmt = select(DBConsumerDlqReplayAudit)
        if recovery_path:
            stmt = stmt.where(DBConsumerDlqReplayAudit.recovery_path == recovery_path)
        if replay_status:
            stmt = stmt.where(DBConsumerDlqReplayAudit.replay_status == replay_status)
        if replay_fingerprint:
            stmt = stmt.where(DBConsumerDlqReplayAudit.replay_fingerprint == replay_fingerprint)
        if job_id:
            stmt = stmt.where(DBConsumerDlqReplayAudit.job_id == job_id)
        rows = (
            await db.scalars(
                stmt.order_by(desc(DBConsumerDlqReplayAudit.requested_at)).limit(limit)
            )
        ).all()
        return [to_replay_audit_response(row) for row in rows]
    return []


async def get_replay_audit_response(
    *,
    replay_id: str,
    session_factory,
) -> IngestionReplayAuditResponse | None:
    async for db in session_factory():
        row = await db.scalar(
            select(DBConsumerDlqReplayAudit)
            .where(DBConsumerDlqReplayAudit.replay_id == replay_id)
            .limit(1)
        )
        return to_replay_audit_response(row) if row else None
    return None


async def find_successful_replay_audit_by_fingerprint_response(
    *,
    replay_fingerprint: str,
    recovery_path: str | None,
    session_factory,
) -> dict[str, str] | None:
    async for db in session_factory():
        stmt = select(DBConsumerDlqReplayAudit).where(
            and_(
                DBConsumerDlqReplayAudit.replay_fingerprint == replay_fingerprint,
                DBConsumerDlqReplayAudit.replay_status.in_(_SUCCESSFUL_REPLAY_AUDIT_STATUSES),
            )
        )
        if recovery_path is not None:
            stmt = stmt.where(DBConsumerDlqReplayAudit.recovery_path == recovery_path)
        row = await db.scalar(stmt.order_by(desc(DBConsumerDlqReplayAudit.requested_at)).limit(1))
        if row is None:
            return None
        return {"replay_id": row.replay_id, "replay_status": row.replay_status}
    return None


async def record_consumer_dlq_replay_audit_response(
    *,
    recovery_path: str,
    event_id: str,
    replay_fingerprint: str,
    correlation_id: str | None,
    job_id: str | None,
    endpoint: str | None,
    replay_status: str,
    dry_run: bool,
    replay_reason: str,
    requested_by: str | None,
    session_factory,
) -> str:
    replay_id = f"replay_{uuid4().hex}"
    async for db in session_factory():
        async with db.begin():
            db.add(
                DBConsumerDlqReplayAudit(
                    replay_id=replay_id,
                    recovery_path=recovery_path,
                    event_id=event_id,
                    replay_fingerprint=replay_fingerprint,
                    correlation_id=correlation_id,
                    job_id=job_id,
                    endpoint=endpoint,
                    replay_status=replay_status,
                    dry_run=dry_run,
                    replay_reason=replay_reason,
                    requested_by=requested_by,
                    completed_at=datetime.now(UTC),
                )
            )
        _record_replay_audit_metrics(
            recovery_path=recovery_path,
            replay_status=replay_status,
        )
        return replay_id
    raise RuntimeError("Unable to record consumer DLQ replay audit.")


def _record_replay_audit_metrics(*, recovery_path: str, replay_status: str) -> None:
    INGESTION_REPLAY_AUDIT_TOTAL.labels(
        recovery_path=recovery_path, replay_status=replay_status
    ).inc()
    if replay_status == "duplicate_blocked":
        INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL.labels(recovery_path=recovery_path).inc()
    if replay_status in _FAILED_REPLAY_AUDIT_STATUSES:
        INGESTION_REPLAY_FAILURE_TOTAL.labels(
            recovery_path=recovery_path, replay_status=replay_status
        ).inc()
