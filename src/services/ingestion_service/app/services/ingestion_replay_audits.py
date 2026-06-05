from __future__ import annotations

from portfolio_common.database_models import ConsumerDlqReplayAudit as DBConsumerDlqReplayAudit
from sqlalchemy import desc, select

from ..DTOs.ingestion_job_dto import IngestionReplayAuditResponse


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
