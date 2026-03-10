# src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import ReprocessingJob
from .utils import async_timed

logger = logging.getLogger(__name__)


class ReprocessingJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="ReprocessingJobRepository", method="create_job")
    async def create_job(self, job_type: str, payload: Dict[str, Any]) -> ReprocessingJob:
        job = ReprocessingJob(job_type=job_type, payload=payload, status="PENDING")
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        logger.info("Created new reprocessing job.", extra={"job_id": job.id, "job_type": job_type})
        return job

    @async_timed(repository="ReprocessingJobRepository", method="find_and_claim_jobs")
    async def find_and_claim_jobs(self, job_type: str, batch_size: int) -> List[ReprocessingJob]:
        """
        Finds PENDING jobs, atomically claims them by updating their
        status to PROCESSING, and returns the claimed jobs.
        """
        query = text(
            """
            UPDATE reprocessing_jobs
            SET status = 'PROCESSING',
                updated_at = now(),
                last_attempted_at = now(),
                attempt_count = attempt_count + 1
            WHERE id IN (
                SELECT id
                FROM reprocessing_jobs
                WHERE status = 'PENDING' AND job_type = :job_type
                ORDER BY created_at ASC, id ASC
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *;
            """
        )
        result = await self.db.execute(
            query,
            {
                "job_type": job_type,
                "batch_size": batch_size,
            },
        )
        claimed_jobs = result.mappings().all()
        return [ReprocessingJob(**job) for job in claimed_jobs]

    @async_timed(repository="ReprocessingJobRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(self, timeout_minutes: int = 15) -> int:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stale_job_ids_stmt = select(ReprocessingJob.id).where(
            ReprocessingJob.status == "PROCESSING",
            ReprocessingJob.updated_at < stale_cutoff,
        )
        stale_job_ids = list((await self.db.execute(stale_job_ids_stmt)).scalars())
        if not stale_job_ids:
            return 0

        stmt = (
            update(ReprocessingJob)
            .where(ReprocessingJob.id.in_(stale_job_ids))
            .values(status="PENDING", updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        return result.rowcount

    @async_timed(repository="ReprocessingJobRepository", method="update_job_status")
    async def update_job_status(
        self, job_id: int, status: str, failure_reason: Optional[str] = None
    ) -> None:
        """Updates the status of a specific job, optionally with a failure reason."""
        values_to_update = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if failure_reason:
            values_to_update["failure_reason"] = failure_reason

        stmt = (
            update(ReprocessingJob).where(ReprocessingJob.id == job_id).values(**values_to_update)
        )
        await self.db.execute(stmt)
