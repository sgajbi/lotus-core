from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import and_, select

from ..DTOs.ingestion_job_dto import (
    IngestionStalledJobListResponse,
    IngestionStalledJobResponse,
)

SessionFactory = Callable[[], AsyncIterator[object]]


def stalled_job_suggested_action(status: str) -> str:
    if status == "accepted":
        return "Investigate consumer lag and retry this job once root cause is resolved."
    return "Inspect downstream processing bottlenecks and verify queued job drain progress."


def to_stalled_job_response(
    row: DBIngestionJob,
    *,
    now: datetime,
) -> IngestionStalledJobResponse:
    return IngestionStalledJobResponse(
        job_id=row.job_id,
        endpoint=row.endpoint,
        entity_type=row.entity_type,
        status=row.status,  # type: ignore[arg-type]
        submitted_at=row.submitted_at,
        queue_age_seconds=float((now - row.submitted_at).total_seconds()),
        retry_count=row.retry_count,
        suggested_action=stalled_job_suggested_action(row.status),
    )


async def load_stalled_job_list_response(
    *,
    threshold_seconds: int,
    limit: int,
    session_factory: SessionFactory,
    now: datetime | None = None,
) -> IngestionStalledJobListResponse:
    now_utc = now or datetime.now(UTC)
    cutoff = now_utc - timedelta(seconds=threshold_seconds)
    async for db in session_factory():
        rows = (
            await db.scalars(
                select(DBIngestionJob)
                .where(
                    and_(
                        DBIngestionJob.status.in_(["accepted", "queued"]),
                        DBIngestionJob.submitted_at <= cutoff,
                    )
                )
                .order_by(DBIngestionJob.submitted_at.asc())
                .limit(limit)
            )
        ).all()
        jobs = [to_stalled_job_response(row, now=now_utc) for row in rows]
        return IngestionStalledJobListResponse(
            threshold_seconds=threshold_seconds,
            total=len(jobs),
            jobs=jobs,
        )

    return IngestionStalledJobListResponse(
        threshold_seconds=threshold_seconds,
        total=0,
        jobs=[],
    )
