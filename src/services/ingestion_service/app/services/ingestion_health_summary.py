from __future__ import annotations

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import case, func, select

from ..DTOs.ingestion_job_dto import IngestionHealthSummaryResponse


async def load_health_summary_response(*, session_factory) -> IngestionHealthSummaryResponse:
    async for db in session_factory():
        row = (
            await db.execute(
                select(
                    func.count(DBIngestionJob.id),
                    func.sum(case((DBIngestionJob.status == "accepted", 1), else_=0)),
                    func.sum(case((DBIngestionJob.status == "queued", 1), else_=0)),
                    func.sum(case((DBIngestionJob.status == "failed", 1), else_=0)),
                )
            )
        ).one()
        total_jobs = int(row[0] or 0)
        accepted_jobs = int(row[1] or 0)
        queued_jobs = int(row[2] or 0)
        failed_jobs = int(row[3] or 0)
        oldest_backlog_job_id = await db.scalar(
            select(DBIngestionJob.job_id)
            .where(DBIngestionJob.status.in_(("accepted", "queued")))
            .order_by(DBIngestionJob.submitted_at.asc(), DBIngestionJob.id.asc())
            .limit(1)
        )
        return IngestionHealthSummaryResponse(
            total_jobs=total_jobs,
            accepted_jobs=accepted_jobs,
            queued_jobs=queued_jobs,
            failed_jobs=failed_jobs,
            backlog_jobs=accepted_jobs + queued_jobs,
            oldest_backlog_job_id=oldest_backlog_job_id,
        )
    return IngestionHealthSummaryResponse(
        total_jobs=0,
        accepted_jobs=0,
        queued_jobs=0,
        failed_jobs=0,
        backlog_jobs=0,
    )
