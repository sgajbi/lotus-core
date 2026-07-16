# src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Date, String, bindparam, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import ReprocessingJob
from .durable_correlation import durable_correlation_diagnostics
from .monitoring import observe_reprocessing_duplicates_normalized
from .utils import async_timed

logger = logging.getLogger(__name__)

EARLIEST_IMPACTED_DATE_JOB_TYPES = frozenset({"RESET_WATERMARKS", "RESET_FX_WATERMARKS"})


def _claim_pending_jobs_query(job_type: str):
    if job_type in EARLIEST_IMPACTED_DATE_JOB_TYPES:
        return text(
            """
            UPDATE reprocessing_jobs
            SET status = 'PROCESSING',
                updated_at = now(),
                last_attempted_at = now(),
                attempt_count = attempt_count + 1
            WHERE status = 'PENDING'
              AND job_type = :job_type
              AND id IN (
                SELECT id
                FROM reprocessing_jobs
                WHERE status = 'PENDING' AND job_type = :job_type
                ORDER BY (payload->>'earliest_impacted_date') ASC, created_at ASC, id ASC
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *;
            """
        )

    return text(
        """
        UPDATE reprocessing_jobs
        SET status = 'PROCESSING',
            updated_at = now(),
            last_attempted_at = now(),
            attempt_count = attempt_count + 1
        WHERE status = 'PENDING'
          AND job_type = :job_type
          AND id IN (
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

    async def stage_pending_fx_revaluation_job(
        self,
        *,
        from_currency: str,
        to_currency: str,
        earliest_impacted_date: date,
        content_hash: str,
        generated_at: str,
        correlation_id: str | None,
        correlation_missing_reason: str | None,
        alternate_lookup_key: str | None,
        attempt_count: int = 0,
    ) -> None:
        """Coalesce one pending FX replay while preserving retry and lineage order."""

        statement = text(
            """
            INSERT INTO reprocessing_jobs (
                job_type,
                payload,
                status,
                attempt_count,
                correlation_id,
                correlation_missing_reason,
                alternate_lookup_key
            )
            VALUES (
                'RESET_FX_WATERMARKS',
                json_build_object(
                    'from_currency', :from_currency,
                    'to_currency', :to_currency,
                    'earliest_impacted_date', CAST(:effective_date AS date)::text,
                    'content_hash', :content_hash,
                    'generated_at', :generated_at
                )::json,
                'PENDING',
                :attempt_count,
                :correlation_id,
                :correlation_missing_reason,
                :alternate_lookup_key
            )
            ON CONFLICT ((payload->>'from_currency'), (payload->>'to_currency'))
            WHERE job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'
            DO UPDATE SET
                payload = json_build_object(
                    'from_currency', :from_currency,
                    'to_currency', :to_currency,
                    'earliest_impacted_date', LEAST(
                        (reprocessing_jobs.payload->>'earliest_impacted_date')::date,
                        CAST(:effective_date AS date)
                    )::text,
                    'content_hash', CASE
                        WHEN ROW(
                            CAST(:generated_at AS timestamptz),
                            :content_hash
                        ) > ROW(
                            COALESCE(
                                CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                                '-infinity'::timestamptz
                            ),
                            COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                        )
                        THEN :content_hash
                        ELSE reprocessing_jobs.payload->>'content_hash'
                    END,
                    'generated_at', CASE
                        WHEN ROW(
                            CAST(:generated_at AS timestamptz),
                            :content_hash
                        ) > ROW(
                            COALESCE(
                                CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                                '-infinity'::timestamptz
                            ),
                            COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                        )
                        THEN :generated_at
                        ELSE reprocessing_jobs.payload->>'generated_at'
                    END
                )::json,
                attempt_count = GREATEST(
                    reprocessing_jobs.attempt_count,
                    EXCLUDED.attempt_count
                ),
                correlation_id = CASE
                    WHEN ROW(
                        CAST(:generated_at AS timestamptz),
                        :content_hash
                    ) > ROW(
                        COALESCE(
                            CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                            '-infinity'::timestamptz
                        ),
                        COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                    )
                    THEN COALESCE(:correlation_id, reprocessing_jobs.correlation_id)
                    ELSE reprocessing_jobs.correlation_id
                END,
                correlation_missing_reason = CASE
                    WHEN ROW(
                        CAST(:generated_at AS timestamptz),
                        :content_hash
                    ) <= ROW(
                        COALESCE(
                            CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                            '-infinity'::timestamptz
                        ),
                        COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                    ) THEN reprocessing_jobs.correlation_missing_reason
                    WHEN :correlation_id IS NOT NULL THEN NULL
                    ELSE reprocessing_jobs.correlation_missing_reason
                END,
                alternate_lookup_key = CASE
                    WHEN ROW(
                        CAST(:generated_at AS timestamptz),
                        :content_hash
                    ) <= ROW(
                        COALESCE(
                            CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                            '-infinity'::timestamptz
                        ),
                        COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                    ) THEN reprocessing_jobs.alternate_lookup_key
                    WHEN :correlation_id IS NOT NULL THEN NULL
                    ELSE reprocessing_jobs.alternate_lookup_key
                END,
                updated_at = now()
            """
        ).bindparams(
            bindparam("from_currency", type_=String()),
            bindparam("to_currency", type_=String()),
            bindparam("effective_date", type_=Date()),
            bindparam("content_hash", type_=String()),
            bindparam("generated_at", type_=String()),
            bindparam("correlation_id", type_=String()),
            bindparam("correlation_missing_reason", type_=String()),
            bindparam("alternate_lookup_key", type_=String()),
        )
        await self.db.execute(
            statement,
            {
                "from_currency": from_currency,
                "to_currency": to_currency,
                "effective_date": earliest_impacted_date,
                "content_hash": content_hash,
                "generated_at": generated_at,
                "attempt_count": attempt_count,
                "correlation_id": correlation_id,
                "correlation_missing_reason": correlation_missing_reason,
                "alternate_lookup_key": alternate_lookup_key,
            },
        )

    @async_timed(repository="ReprocessingJobRepository", method="create_job")
    async def create_job(
        self,
        job_type: str,
        payload: Dict[str, Any],
        correlation_id: str | None = None,
        *,
        attempt_count: int = 0,
    ) -> ReprocessingJob:
        diagnostics = _reprocessing_job_correlation_diagnostics(
            job_type=job_type,
            payload=payload,
            correlation_id=correlation_id,
        )
        correlation_id = diagnostics.correlation_id
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
                    correlation_id,
                    correlation_missing_reason,
                    alternate_lookup_key
                )
                VALUES (
                    'RESET_WATERMARKS',
                    json_build_object(
                        'security_id', :security_id,
                        'earliest_impacted_date', :earliest_impacted_date
                    )::json,
                    'PENDING',
                    :attempt_count,
                    :correlation_id,
                    :correlation_missing_reason,
                    :alternate_lookup_key
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
                    attempt_count = GREATEST(
                        reprocessing_jobs.attempt_count,
                        EXCLUDED.attempt_count
                    ),
                    correlation_id = CASE
                        WHEN CAST(:earliest_impacted_date AS date)
                             < (reprocessing_jobs.payload->>'earliest_impacted_date')::date
                        THEN COALESCE(:correlation_id, reprocessing_jobs.correlation_id)
                        WHEN reprocessing_jobs.correlation_id IS NULL
                        THEN :correlation_id
                        ELSE reprocessing_jobs.correlation_id
                    END,
                    correlation_missing_reason = CASE
                        WHEN :correlation_id IS NOT NULL
                        THEN NULL
                        WHEN reprocessing_jobs.correlation_id IS NULL
                             AND CAST(:earliest_impacted_date AS date) <
                                 CAST(reprocessing_jobs.payload->>'earliest_impacted_date' AS date)
                        THEN :correlation_missing_reason
                        WHEN reprocessing_jobs.correlation_id IS NULL
                             AND reprocessing_jobs.correlation_missing_reason IS NULL
                        THEN :correlation_missing_reason
                        ELSE reprocessing_jobs.correlation_missing_reason
                    END,
                    alternate_lookup_key = CASE
                        WHEN :correlation_id IS NOT NULL
                        THEN NULL
                        WHEN reprocessing_jobs.correlation_id IS NULL
                             AND CAST(:earliest_impacted_date AS date) <
                                 CAST(reprocessing_jobs.payload->>'earliest_impacted_date' AS date)
                        THEN :alternate_lookup_key
                        WHEN reprocessing_jobs.correlation_id IS NULL
                             AND reprocessing_jobs.alternate_lookup_key IS NULL
                        THEN :alternate_lookup_key
                        ELSE reprocessing_jobs.alternate_lookup_key
                    END,
                    updated_at = now()
                RETURNING *;
                """
            ).bindparams(
                bindparam("security_id", type_=String()),
                bindparam("earliest_impacted_date", type_=Date()),
                bindparam("correlation_id", type_=String()),
                bindparam("correlation_missing_reason", type_=String()),
                bindparam("alternate_lookup_key", type_=String()),
            )
            result = await self.db.execute(
                stmt,
                {
                    "security_id": payload["security_id"],
                    "earliest_impacted_date": date.fromisoformat(payload["earliest_impacted_date"]),
                    "attempt_count": attempt_count,
                    "correlation_id": correlation_id,
                    "correlation_missing_reason": diagnostics.correlation_missing_reason,
                    "alternate_lookup_key": diagnostics.alternate_lookup_key,
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
            attempt_count=attempt_count,
            correlation_id=correlation_id,
            correlation_missing_reason=diagnostics.correlation_missing_reason,
            alternate_lookup_key=diagnostics.alternate_lookup_key,
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
        if job_type == "RESET_WATERMARKS":
            normalized_count = await self.normalize_pending_reset_watermarks_duplicates()
            if normalized_count:
                logger.info(
                    "Normalized duplicate pending reset-watermarks jobs before claim.",
                    extra={"deleted_count": normalized_count},
                )

        query = _claim_pending_jobs_query(job_type)
        result = await self.db.execute(
            query,
            {
                "job_type": job_type,
                "batch_size": batch_size,
            },
        )
        claimed_jobs = result.mappings().all()
        jobs = [ReprocessingJob(**job) for job in claimed_jobs]
        if job_type in EARLIEST_IMPACTED_DATE_JOB_TYPES:
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
        stale_rows = await self._find_stale_job_rows(stale_cutoff)
        if not stale_rows:
            return 0

        handled_job_ids, recovered_count = await self._recover_retryable_stale_coalesced_jobs(
            stale_rows,
            stale_cutoff=stale_cutoff,
            max_attempts=max_attempts,
        )

        failed_job_ids = _over_limit_stale_job_ids(stale_rows, max_attempts)
        reset_job_ids = [
            job_id
            for job_id in _resettable_stale_job_ids(stale_rows, max_attempts)
            if job_id not in handled_job_ids
        ]

        await self._mark_over_limit_stale_jobs_failed(
            failed_job_ids,
            stale_cutoff,
            max_attempts,
        )
        reset_count = await self._reset_retryable_stale_jobs(reset_job_ids, stale_cutoff)
        return recovered_count + reset_count

    async def _find_stale_job_rows(self, stale_cutoff: datetime) -> list[Any]:
        return (await self.db.execute(_stale_reprocessing_jobs_stmt(stale_cutoff))).all()

    async def _recover_retryable_stale_coalesced_jobs(
        self,
        stale_rows: list[Any],
        *,
        stale_cutoff: datetime,
        max_attempts: int,
    ) -> tuple[set[int], int]:
        handled_job_ids: set[int] = set()
        recovered_count = 0
        for row in stale_rows:
            if row.job_type not in EARLIEST_IMPACTED_DATE_JOB_TYPES:
                continue
            if row.attempt_count >= max_attempts:
                continue
            try:
                payload = row.payload
                if row.job_type == "RESET_FX_WATERMARKS":
                    await self.stage_pending_fx_revaluation_job(
                        from_currency=payload["from_currency"],
                        to_currency=payload["to_currency"],
                        earliest_impacted_date=date.fromisoformat(
                            payload["earliest_impacted_date"]
                        ),
                        content_hash=payload["content_hash"],
                        generated_at=payload["generated_at"],
                        correlation_id=row.correlation_id,
                        correlation_missing_reason=row.correlation_missing_reason,
                        alternate_lookup_key=row.alternate_lookup_key,
                        attempt_count=int(row.attempt_count),
                    )
                    completion_reason = "Coalesced into pending FX replay during stale recovery"
                else:
                    await self.create_job(
                        row.job_type,
                        payload,
                        correlation_id=row.correlation_id,
                        attempt_count=int(row.attempt_count),
                    )
                    completion_reason = (
                        "Coalesced into pending security replay during stale recovery"
                    )
            except (KeyError, TypeError, ValueError):
                logger.warning(
                    "Skipped malformed stale replay during identity coalescing.",
                    extra={"job_id": row.id, "job_type": row.job_type},
                )
                result = await self.db.execute(
                    _stale_jobs_update_stmt([row.id], stale_cutoff).values(
                        status="FAILED",
                        failure_reason="Malformed effective-dated replay during stale recovery",
                        updated_at=func.now(),
                    )
                )
                if int(result.rowcount or 0) == 1:
                    handled_job_ids.add(int(row.id))
                continue

            result = await self.db.execute(
                _stale_jobs_update_stmt([row.id], stale_cutoff).values(
                    status="COMPLETE",
                    failure_reason=completion_reason,
                    updated_at=func.now(),
                )
            )
            if int(result.rowcount or 0) == 1:
                handled_job_ids.add(int(row.id))
                recovered_count += 1
        return handled_job_ids, recovered_count

    async def _mark_over_limit_stale_jobs_failed(
        self,
        failed_job_ids: list[int],
        stale_cutoff: datetime,
        max_attempts: int,
    ) -> None:
        if not failed_job_ids:
            return
        await self.db.execute(_failed_stale_jobs_update_stmt(failed_job_ids, stale_cutoff))
        logger.warning(
            "Marked stale reprocessing jobs as FAILED after max attempts.",
            extra={"job_ids": failed_job_ids, "max_attempts": max_attempts},
        )

    async def _reset_retryable_stale_jobs(
        self,
        reset_job_ids: list[int],
        stale_cutoff: datetime,
    ) -> int:
        if not reset_job_ids:
            return 0
        result = await self.db.execute(_reset_stale_jobs_update_stmt(reset_job_ids, stale_cutoff))
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
    ) -> bool:
        """Updates the status of a specific job, optionally with a failure reason."""
        values_to_update = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if failure_reason:
            values_to_update["failure_reason"] = failure_reason

        stmt = (
            update(ReprocessingJob)
            .where(
                ReprocessingJob.id == job_id,
                ReprocessingJob.status == "PROCESSING",
            )
            .values(**values_to_update)
        )
        result = await self.db.execute(stmt)
        return result.rowcount == 1


def _over_limit_stale_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [row.id for row in stale_rows if row.attempt_count >= max_attempts]


def _resettable_stale_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [row.id for row in stale_rows if row.attempt_count < max_attempts]


def _stale_reprocessing_jobs_stmt(stale_cutoff: datetime):
    return (
        select(
            ReprocessingJob.id,
            ReprocessingJob.attempt_count,
            ReprocessingJob.job_type,
            ReprocessingJob.payload,
            ReprocessingJob.correlation_id,
            ReprocessingJob.correlation_missing_reason,
            ReprocessingJob.alternate_lookup_key,
        )
        .where(
            ReprocessingJob.status == "PROCESSING",
            ReprocessingJob.updated_at < stale_cutoff,
        )
        .order_by(ReprocessingJob.id.asc())
    )


def _failed_stale_jobs_update_stmt(failed_job_ids: list[int], stale_cutoff: datetime):
    return (
        _stale_jobs_update_stmt(failed_job_ids, stale_cutoff)
        .values(
            status="FAILED",
            failure_reason="Stale processing timeout exceeded max attempts",
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _reset_stale_jobs_update_stmt(reset_job_ids: list[int], stale_cutoff: datetime):
    return (
        _stale_jobs_update_stmt(reset_job_ids, stale_cutoff)
        .values(status="PENDING", updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


def _stale_jobs_update_stmt(job_ids: list[int], stale_cutoff: datetime):
    return update(ReprocessingJob).where(
        ReprocessingJob.id.in_(job_ids),
        ReprocessingJob.status == "PROCESSING",
        ReprocessingJob.updated_at < stale_cutoff,
    )


def _reprocessing_job_correlation_diagnostics(
    *,
    job_type: str,
    payload: Dict[str, Any],
    correlation_id: str | None,
):
    return durable_correlation_diagnostics(
        correlation_id=correlation_id,
        record_family="reprocessing_job",
        job_type=job_type,
        security_id=payload.get("security_id"),
        earliest_impacted_date=payload.get("earliest_impacted_date"),
    )
