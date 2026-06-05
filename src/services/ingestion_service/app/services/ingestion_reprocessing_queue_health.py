from __future__ import annotations

from datetime import UTC, datetime

from portfolio_common.database_models import ReprocessingJob as DBReprocessingJob
from sqlalchemy import case, func, select

from ..DTOs.ingestion_job_dto import (
    IngestionReprocessingQueueHealthResponse,
    IngestionReprocessingQueueItemResponse,
)


async def load_reprocessing_queue_health_response(
    *,
    session_factory,
) -> IngestionReprocessingQueueHealthResponse:
    now = datetime.now(UTC)
    async for db in session_factory():
        stmt = select(
            DBReprocessingJob.job_type.label("job_type"),
            func.sum(case((DBReprocessingJob.status == "PENDING", 1), else_=0)).label(
                "pending_jobs"
            ),
            func.sum(case((DBReprocessingJob.status == "PROCESSING", 1), else_=0)).label(
                "processing_jobs"
            ),
            func.sum(case((DBReprocessingJob.status == "FAILED", 1), else_=0)).label("failed_jobs"),
            func.min(
                case(
                    (DBReprocessingJob.status == "PENDING", DBReprocessingJob.created_at),
                    else_=None,
                )
            ).label("oldest_pending_created_at"),
        ).group_by(DBReprocessingJob.job_type)
        result = await db.execute(stmt)
        rows = result.mappings().all()
        break
    else:
        rows = []

    queue_items: list[IngestionReprocessingQueueItemResponse] = []
    total_pending = 0
    total_processing = 0
    total_failed = 0
    for row in rows:
        oldest_pending_created_at = row["oldest_pending_created_at"]
        oldest_pending_age_seconds = (
            max(0.0, (now - oldest_pending_created_at).total_seconds())
            if oldest_pending_created_at
            else 0.0
        )
        pending_jobs = int(row["pending_jobs"] or 0)
        processing_jobs = int(row["processing_jobs"] or 0)
        failed_jobs = int(row["failed_jobs"] or 0)
        queue_items.append(
            IngestionReprocessingQueueItemResponse(
                job_type=row["job_type"],
                pending_jobs=pending_jobs,
                processing_jobs=processing_jobs,
                failed_jobs=failed_jobs,
                oldest_pending_created_at=oldest_pending_created_at,
                oldest_pending_age_seconds=oldest_pending_age_seconds,
            )
        )
        total_pending += pending_jobs
        total_processing += processing_jobs
        total_failed += failed_jobs

    queue_items.sort(
        key=lambda item: (
            item.pending_jobs,
            item.processing_jobs,
            item.oldest_pending_age_seconds,
            item.job_type,
        ),
        reverse=True,
    )
    return IngestionReprocessingQueueHealthResponse(
        as_of=now,
        total_pending_jobs=total_pending,
        total_processing_jobs=total_processing,
        total_failed_jobs=total_failed,
        queues=queue_items,
    )
