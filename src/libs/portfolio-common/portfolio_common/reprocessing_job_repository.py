# src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Date, String, bindparam, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import ReprocessingJob
from .logging_utils import normalize_lineage_value
from .monitoring import observe_reprocessing_duplicates_normalized
from .utils import async_timed

logger = logging.getLogger(__name__)


class ReprocessingJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def normalize_pending_reset_watermarks_duplicates(self) -> int:
        """
        Coalesces any historically duplicated pending RESET_WATERMARKS jobs so that
        one pending job remains per security_id with the earliest impacted date.
        Returns the number of redundant rows removed.
        """
        normalize_stmt = text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    payload->>'security_id' AS security_id,
                    (payload->>'earliest_impacted_date')::date AS earliest_impacted_date,
                    row_number() OVER (
                        PARTITION BY payload->>'security_id'
                        ORDER BY
                            (payload->>'earliest_impacted_date')::date ASC,
                            created_at ASC,
                            id ASC
                    ) AS rn,
                    min((payload->>'earliest_impacted_date')::date) OVER (
                        PARTITION BY payload->>'security_id'
                    ) AS min_impacted_date
                FROM reprocessing_jobs
                WHERE status = 'PENDING' AND job_type = 'RESET_WATERMARKS'
            ),
            keepers AS (
                UPDATE reprocessing_jobs j
                SET payload = jsonb_set(
                        j.payload::jsonb,
                        '{earliest_impacted_date}',
                        to_jsonb(r.min_impacted_date::text)
                    )::json,
                    updated_at = now()
                FROM ranked r
                WHERE j.id = r.id
                  AND r.rn = 1
                  AND (j.payload->>'earliest_impacted_date')::date <> r.min_impacted_date
                RETURNING j.id
            ),
            deleted AS (
                DELETE FROM reprocessing_jobs j
                USING ranked r
                WHERE j.id = r.id
                  AND r.rn > 1
                RETURNING j.id
            )
            SELECT count(*) FROM deleted;
            """
        )
        result = await self.db.execute(normalize_stmt)
        deleted_count = int(result.scalar_one())
        if deleted_count:
            observe_reprocessing_duplicates_normalized(
                "reset_watermarks_pending_jobs",
                deleted_count,
            )
        return deleted_count

    @async_timed(repository="ReprocessingJobRepository", method="create_job")
    async def create_job(
        self, job_type: str, payload: Dict[str, Any], correlation_id: str | None = None
    ) -> ReprocessingJob:
        correlation_id = normalize_lineage_value(correlation_id)
        if (
            job_type == "RESET_WATERMARKS"
            and payload.get("security_id")
            and payload.get("earliest_impacted_date")
        ):
            stmt = text(
                """
                INSERT INTO reprocessing_jobs (
                    job_type,
                    payload,
                    status,
                    attempt_count,
                    correlation_id
                )
                VALUES (
                    'RESET_WATERMARKS',
                    json_build_object(
                        'security_id', :security_id,
                        'earliest_impacted_date', :earliest_impacted_date
                    )::json,
                    'PENDING',
                    0,
                    :correlation_id
                )
                ON CONFLICT ((payload->>'security_id'))
                WHERE job_type = 'RESET_WATERMARKS' AND status = 'PENDING'
                DO UPDATE
                SET payload = jsonb_set(
                        reprocessing_jobs.payload::jsonb,
                        '{earliest_impacted_date}',
                        to_jsonb(
                            LEAST(
                                (reprocessing_jobs.payload->>'earliest_impacted_date')::date,
                                CAST(:earliest_impacted_date AS date)
                            )::text
                        )
                    )::json,
                    correlation_id = CASE
                        WHEN CAST(:earliest_impacted_date AS date)
                             < (reprocessing_jobs.payload->>'earliest_impacted_date')::date
                        THEN COALESCE(:correlation_id, reprocessing_jobs.correlation_id)
                        WHEN reprocessing_jobs.correlation_id IS NULL
                        THEN :correlation_id
                        ELSE reprocessing_jobs.correlation_id
                    END,
                    updated_at = now()
                RETURNING *;
                """
            ).bindparams(
                bindparam("security_id", type_=String()),
                bindparam("earliest_impacted_date", type_=Date()),
                bindparam("correlation_id", type_=String()),
            )
            result = await self.db.execute(
                stmt,
                {
                    "security_id": payload["security_id"],
                    "earliest_impacted_date": date.fromisoformat(payload["earliest_impacted_date"]),
                    "correlation_id": correlation_id,
                },
            )
            job = ReprocessingJob(**result.mappings().one())
            logger.info(
                "Coalesced reset-watermarks reprocessing job.",
                extra={
                    "job_id": job.id,
                    "security_id": payload["security_id"],
                },
            )
            return job

        job = ReprocessingJob(
            job_type=job_type,
            payload=payload,
            status="PENDING",
            correlation_id=correlation_id,
        )
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
        order_clause = "created_at ASC, id ASC"
        if job_type == "RESET_WATERMARKS":
            normalized_count = await self.normalize_pending_reset_watermarks_duplicates()
            if normalized_count:
                logger.info(
                    "Normalized duplicate pending reset-watermarks jobs before claim.",
                    extra={"deleted_count": normalized_count},
                )
            order_clause = "(payload->>'earliest_impacted_date') ASC, " "created_at ASC, id ASC"

        query = text(
            f"""
            UPDATE reprocessing_jobs
            SET status = 'PROCESSING',
                updated_at = now(),
                last_attempted_at = now(),
                attempt_count = attempt_count + 1
            WHERE id IN (
                SELECT id
                FROM reprocessing_jobs
                WHERE status = 'PENDING' AND job_type = :job_type
                ORDER BY {order_clause}
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
        jobs = [ReprocessingJob(**job) for job in claimed_jobs]
        if job_type == "RESET_WATERMARKS":
            jobs.sort(
                key=lambda job: (
                    date.fromisoformat(job.payload["earliest_impacted_date"]),
                    job.created_at,
                    job.id,
                )
            )
        else:
            jobs.sort(key=lambda job: (job.created_at, job.id))
        return jobs

    @async_timed(repository="ReprocessingJobRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(
        self, timeout_minutes: int = 15, max_attempts: int = 3
    ) -> int:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stale_jobs_stmt = select(ReprocessingJob.id, ReprocessingJob.attempt_count).where(
            ReprocessingJob.status == "PROCESSING",
            ReprocessingJob.updated_at < stale_cutoff,
        )
        stale_rows = (await self.db.execute(stale_jobs_stmt)).all()
        if not stale_rows:
            return 0

        failed_job_ids = [row.id for row in stale_rows if row.attempt_count >= max_attempts]
        reset_job_ids = [row.id for row in stale_rows if row.attempt_count < max_attempts]

        if failed_job_ids:
            failure_stmt = (
                update(ReprocessingJob)
                .where(
                    ReprocessingJob.id.in_(failed_job_ids),
                    ReprocessingJob.status == "PROCESSING",
                    ReprocessingJob.updated_at < stale_cutoff,
                )
                .values(
                    status="FAILED",
                    failure_reason="Stale processing timeout exceeded max attempts",
                    updated_at=func.now(),
                )
                .execution_options(synchronize_session=False)
            )
            await self.db.execute(failure_stmt)
            logger.warning(
                "Marked stale reprocessing jobs as FAILED after max attempts.",
                extra={"job_ids": failed_job_ids, "max_attempts": max_attempts},
            )

        if not reset_job_ids:
            return 0

        stmt = (
            update(ReprocessingJob)
            .where(
                ReprocessingJob.id.in_(reset_job_ids),
                ReprocessingJob.status == "PROCESSING",
                ReprocessingJob.updated_at < stale_cutoff,
            )
            .values(status="PENDING", updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        return result.rowcount

    @async_timed(repository="ReprocessingJobRepository", method="get_queue_stats")
    async def get_queue_stats(self, job_type: str | None = None) -> Dict[str, Any]:
        stmt = select(
            func.count().filter(ReprocessingJob.status == "PENDING").label("pending_count"),
            func.count().filter(ReprocessingJob.status == "FAILED").label("failed_count"),
            func.min(ReprocessingJob.created_at)
            .filter(ReprocessingJob.status == "PENDING")
            .label("oldest_pending_created_at"),
        )
        if job_type is not None:
            stmt = stmt.where(ReprocessingJob.job_type == job_type)
        row = (await self.db.execute(stmt)).one()
        return {
            "pending_count": int(row.pending_count or 0),
            "failed_count": int(row.failed_count or 0),
            "oldest_pending_created_at": row.oldest_pending_created_at,
        }

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
