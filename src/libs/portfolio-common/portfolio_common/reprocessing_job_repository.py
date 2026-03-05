# src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import ReprocessingJob

logger = logging.getLogger(__name__)

class ReprocessingJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, job_type: str, payload: Dict[str, Any]) -> ReprocessingJob:
        job = ReprocessingJob(
            job_type=job_type,
            payload=payload,
            status='PENDING'
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        logger.info(f"Created new reprocessing job.", extra={"job_id": job.id, "job_type": job_type})
        return job
        
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

    async def update_job_status(
        self, job_id: int, status: str, failure_reason: Optional[str] = None
    ) -> None:
        """Updates the status of a specific job, optionally with a failure reason."""
        values_to_update = {
            "status": status,
            "updated_at": datetime.now(timezone.utc)
        }
        if failure_reason:
            values_to_update["failure_reason"] = failure_reason

        stmt = (
            update(ReprocessingJob)
            .where(ReprocessingJob.id == job_id)
            .values(**values_to_update)
        )
        await self.db.execute(stmt)
