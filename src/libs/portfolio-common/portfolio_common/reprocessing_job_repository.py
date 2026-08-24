# src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Dict, Optional, cast

from sqlalchemy import Date, String, bindparam, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import ReprocessingJob
from .durable_correlation import durable_correlation_diagnostics
from .infrastructure.persistence.statement_batching import (
    POSTGRES_STATEMENT_ROW_LIMIT,
    StatementBatchOperation,
    iter_statement_chunks,
    observe_multi_statement_batch,
)
from .monitoring import observe_reprocessing_duplicates_normalized
from .utils import async_timed

logger = logging.getLogger(__name__)

EARLIEST_IMPACTED_DATE_JOB_TYPES = frozenset({"RESET_WATERMARKS", "RESET_FX_WATERMARKS"})
_STALE_FAILED_RESERVED_BINDS = 7
_STALE_RESET_RESERVED_BINDS = 5
_LEASE_OWNER_MAX_LENGTH = 128
_DEFAULT_LEASE_DURATION_SECONDS = 15 * 60
_OWNED_TRANSITION_STATUSES = frozenset({"PENDING", "COMPLETE", "FAILED"})


class ResetWatermarksStageOutcome(StrEnum):
    """Bounded persistence outcome for one reset-watermarks staging request."""

    CREATED = "created"
    COALESCED_PENDING = "coalesced_pending"


class ReprocessingJobTransitionOutcome(StrEnum):
    """Classify an exact owned transition without overstating lease authority."""

    APPLIED = "APPLIED"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    TOKEN_MISMATCH = "TOKEN_MISMATCH"
    NOT_PROCESSING = "NOT_PROCESSING"
    NOT_FOUND = "NOT_FOUND"
    RACED = "RACED"


@dataclass(frozen=True)
class ResetWatermarksStageResult:
    """Durable job plus the exact pending-job upsert outcome."""

    job: ReprocessingJob
    outcome: ResetWatermarksStageOutcome


@dataclass(frozen=True, slots=True)
class ClaimedReprocessingJob:
    """Immutable work authority that remains valid outside the claim transaction."""

    id: int
    job_type: str
    payload: dict[str, Any]
    status: str
    correlation_id: str | None
    correlation_missing_reason: str | None
    alternate_lookup_key: str | None
    attempt_count: int
    created_at: datetime
    lease_token: str
    lease_expires_at: datetime


def _claim_pending_jobs_query(job_type: str):
    if job_type in EARLIEST_IMPACTED_DATE_JOB_TYPES:
        return text(
            """
            UPDATE reprocessing_jobs
            SET status = 'PROCESSING',
                updated_at = now(),
                last_attempted_at = now(),
                attempt_count = attempt_count + 1,
                lease_owner = :lease_owner,
                lease_token = :lease_token,
                lease_expires_at = clock_timestamp()
                    + make_interval(secs => :lease_duration_seconds)
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
            attempt_count = attempt_count + 1,
            lease_owner = :lease_owner,
            lease_token = :lease_token,
            lease_expires_at = clock_timestamp()
                + make_interval(secs => :lease_duration_seconds)
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
        self._default_lease_owner = f"reprocessing-repository-{uuid.uuid4().hex}"

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
        """Quarantine malformed pair work, then coalesce one valid pending FX replay."""

        quarantine_statement = text(
            """
            UPDATE reprocessing_jobs
            SET status = 'FAILED',
                failure_reason = (
                    'invalid_fx_revaluation_job_payload: '
                    'superseded during valid replay staging'
                ),
                updated_at = now()
            WHERE job_type = 'RESET_FX_WATERMARKS'
              AND status = 'PENDING'
              AND payload->>'from_currency' = :from_currency
              AND payload->>'to_currency' = :to_currency
              AND (
                  pg_input_is_valid(
                      payload->>'earliest_impacted_date',
                      'date'
                  ) IS NOT TRUE
                  OR pg_input_is_valid(
                      payload->>'generated_at',
                      'timestamp with time zone'
                  ) IS NOT TRUE
              )
            """
        ).bindparams(
            bindparam("from_currency", type_=String()),
            bindparam("to_currency", type_=String()),
        )
        await self.db.execute(
            quarantine_statement,
            {
                "from_currency": from_currency,
                "to_currency": to_currency,
            },
        )

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
            return (
                await self.stage_reset_watermarks_job(
                    security_id=str(payload["security_id"]),
                    earliest_impacted_date=date.fromisoformat(payload["earliest_impacted_date"]),
                    correlation_id=correlation_id,
                    attempt_count=attempt_count,
                )
            ).job

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

    @async_timed(repository="ReprocessingJobRepository", method="stage_reset_watermarks_job")
    async def stage_reset_watermarks_job(
        self,
        *,
        security_id: str,
        earliest_impacted_date: date,
        correlation_id: str | None,
        attempt_count: int = 0,
    ) -> ResetWatermarksStageResult:
        """Create or coalesce one pending reset job without committing the caller's UoW."""
        payload = {
            "security_id": security_id,
            "earliest_impacted_date": earliest_impacted_date.isoformat(),
        }
        diagnostics = _reprocessing_job_correlation_diagnostics(
            job_type="RESET_WATERMARKS",
            payload=payload,
            correlation_id=correlation_id,
        )
        correlation_id = diagnostics.correlation_id
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
                RETURNING *, (xmax = 0) AS was_inserted;
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
                "security_id": security_id,
                "earliest_impacted_date": earliest_impacted_date,
                "attempt_count": attempt_count,
                "correlation_id": correlation_id,
                "correlation_missing_reason": diagnostics.correlation_missing_reason,
                "alternate_lookup_key": diagnostics.alternate_lookup_key,
            },
        )
        row = dict(result.mappings().one())
        was_inserted = bool(row.pop("was_inserted"))
        job = ReprocessingJob(**row)
        outcome = (
            ResetWatermarksStageOutcome.CREATED
            if was_inserted
            else ResetWatermarksStageOutcome.COALESCED_PENDING
        )
        logger.info(
            "Staged reset-watermarks reprocessing job.",
            extra={
                "job_id": job.id,
                "security_id": security_id,
                "outcome": outcome.value,
            },
        )
        return ResetWatermarksStageResult(job=job, outcome=outcome)

    @async_timed(repository="ReprocessingJobRepository", method="find_and_claim_jobs")
    async def find_and_claim_jobs(
        self,
        job_type: str,
        batch_size: int,
        *,
        lease_owner: str | None = None,
        lease_duration_seconds: int = _DEFAULT_LEASE_DURATION_SECONDS,
    ) -> list[ClaimedReprocessingJob]:
        """
        Finds PENDING jobs, atomically claims them by updating their
        status to PROCESSING, and returns the claimed jobs.
        """
        resolved_lease_owner = (lease_owner or self._default_lease_owner).strip()
        if not resolved_lease_owner or len(resolved_lease_owner) > _LEASE_OWNER_MAX_LENGTH:
            raise ValueError("reprocessing lease owner must contain 1 to 128 characters")
        if lease_duration_seconds < 1:
            raise ValueError("reprocessing lease duration must be positive")

        if job_type == "RESET_WATERMARKS":
            normalized_count = await self.normalize_pending_reset_watermarks_duplicates()
            if normalized_count:
                logger.info(
                    "Normalized duplicate pending reset-watermarks jobs before claim.",
                    extra={"deleted_count": normalized_count},
                )

        query = _claim_pending_jobs_query(job_type)
        lease_token = uuid.uuid4().hex
        result = await self.db.execute(
            query,
            {
                "job_type": job_type,
                "batch_size": batch_size,
                "lease_owner": resolved_lease_owner,
                "lease_token": lease_token,
                "lease_duration_seconds": lease_duration_seconds,
            },
        )
        claimed_jobs = result.mappings().all()
        jobs = [_claimed_reprocessing_job(job) for job in claimed_jobs]
        if job_type in EARLIEST_IMPACTED_DATE_JOB_TYPES:
            jobs.sort(key=_effective_date_job_priority)
        else:
            jobs.sort(key=lambda job: (job.created_at, job.id))
        return jobs

    @async_timed(repository="ReprocessingJobRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(self, max_attempts: int = 3) -> int:
        """Recover jobs whose database-clock lease has expired."""

        stale_rows = await self._find_stale_job_rows()
        if not stale_rows:
            return 0

        handled_job_ids, recovered_count = await self._recover_retryable_stale_coalesced_jobs(
            stale_rows,
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
            max_attempts,
        )
        reset_count = await self._reset_retryable_stale_jobs(reset_job_ids)
        return recovered_count + reset_count

    async def _find_stale_job_rows(self) -> list[Any]:
        return (await self.db.execute(_stale_reprocessing_jobs_stmt())).all()

    async def _recover_retryable_stale_coalesced_jobs(
        self,
        stale_rows: list[Any],
        *,
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
                    extra={
                        "event_name": "reprocessing_stale_recovery",
                        "operation": "fail_malformed",
                        "status": "staged",
                        "reason_code": "malformed_effective_dated_payload",
                        "job_type": row.job_type,
                    },
                )
                result = await self.db.execute(
                    _stale_jobs_update_stmt([row.id]).values(
                        status="FAILED",
                        lease_owner=None,
                        lease_token=None,
                        lease_expires_at=None,
                        failure_reason="Malformed effective-dated replay during stale recovery",
                        updated_at=func.now(),
                    )
                )
                if int(result.rowcount or 0) == 1:
                    handled_job_ids.add(int(row.id))
                continue

            result = await self.db.execute(
                _stale_jobs_update_stmt([row.id]).values(
                    status="COMPLETE",
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
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
        max_attempts: int,
    ) -> None:
        normalized_job_ids = sorted(set(failed_job_ids))
        if not normalized_job_ids:
            return
        observe_multi_statement_batch(
            operation=StatementBatchOperation.REPROCESSING_STALE_FAILED_UPDATE,
            item_count=len(normalized_job_ids),
            binds_per_row=1,
            reserved_binds=_STALE_FAILED_RESERVED_BINDS,
        )
        for job_id_chunk in iter_statement_chunks(
            normalized_job_ids,
            binds_per_row=1,
            reserved_binds=_STALE_FAILED_RESERVED_BINDS,
        ):
            await self.db.execute(_failed_stale_jobs_update_stmt(list(job_id_chunk)))
        logger.warning(
            "Marked stale reprocessing jobs as FAILED after max attempts.",
            extra={
                "event_name": "reprocessing_stale_recovery",
                "operation": "fail_over_limit",
                "status": "staged",
                "reason_code": "max_attempts_exceeded",
                "job_count": len(normalized_job_ids),
                "max_attempts": max_attempts,
            },
        )

    async def _reset_retryable_stale_jobs(
        self,
        reset_job_ids: list[int],
    ) -> int:
        normalized_job_ids = sorted(set(reset_job_ids))
        if not normalized_job_ids:
            return 0
        observe_multi_statement_batch(
            operation=StatementBatchOperation.REPROCESSING_STALE_RESET_UPDATE,
            item_count=len(normalized_job_ids),
            binds_per_row=1,
            reserved_binds=_STALE_RESET_RESERVED_BINDS,
        )
        reset_count = 0
        for job_id_chunk in iter_statement_chunks(
            normalized_job_ids,
            binds_per_row=1,
            reserved_binds=_STALE_RESET_RESERVED_BINDS,
        ):
            result = await self.db.execute(_reset_stale_jobs_update_stmt(list(job_id_chunk)))
            reset_count += int(result.rowcount or 0)
        return reset_count

    @async_timed(repository="ReprocessingJobRepository", method="get_queue_stats")
    async def get_queue_stats(self, job_type: str | None = None) -> Dict[str, Any]:
        stmt = select(
            func.count().filter(ReprocessingJob.status == "PENDING").label("pending_count"),
            func.count().filter(ReprocessingJob.status == "FAILED").label("failed_count"),
            func.min(ReprocessingJob.created_at)
            .filter(ReprocessingJob.status == "PENDING")
            .label("oldest_pending_created_at"),
        ).where(ReprocessingJob.status.in_(("PENDING", "FAILED")))
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
        self,
        job_id: int,
        status: str,
        *,
        lease_token: str,
        failure_reason: Optional[str] = None,
    ) -> ReprocessingJobTransitionOutcome:
        """Apply a transition only for the exact, still-live database claim."""

        if not lease_token:
            raise ValueError("reprocessing lease token is required")
        if status not in _OWNED_TRANSITION_STATUSES:
            raise ValueError("reprocessing owned transition status is invalid")
        if failure_reason is not None and status != "FAILED":
            raise ValueError("reprocessing failure reason requires FAILED status")
        if status == "FAILED" and (failure_reason is None or not failure_reason.strip()):
            raise ValueError("reprocessing FAILED transition requires a failure reason")
        values_to_update = {
            "status": status,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "updated_at": func.now(),
        }
        if failure_reason:
            values_to_update["failure_reason"] = failure_reason

        stmt = (
            update(ReprocessingJob)
            .where(
                ReprocessingJob.id == job_id,
                ReprocessingJob.status == "PROCESSING",
                ReprocessingJob.lease_token == lease_token,
                ReprocessingJob.lease_expires_at > func.clock_timestamp(),
            )
            .values(**values_to_update)
        )
        result = await self.db.execute(stmt)
        if result.rowcount == 1:
            return ReprocessingJobTransitionOutcome.APPLIED

        return await self._classify_owned_transition_failure(job_id, lease_token)

    @async_timed(repository="ReprocessingJobRepository", method="renew_lease")
    async def renew_lease(
        self,
        job_id: int,
        *,
        lease_token: str,
        lease_duration_seconds: int,
    ) -> ReprocessingJobTransitionOutcome:
        """Extend an exact live claim using only the PostgreSQL clock."""

        if not lease_token:
            raise ValueError("reprocessing lease token is required")
        if lease_duration_seconds <= 0:
            raise ValueError("reprocessing lease duration must be positive")

        stmt = (
            update(ReprocessingJob)
            .where(
                ReprocessingJob.id == job_id,
                ReprocessingJob.status == "PROCESSING",
                ReprocessingJob.lease_token == lease_token,
                ReprocessingJob.lease_expires_at > func.clock_timestamp(),
            )
            .values(
                lease_expires_at=func.clock_timestamp()
                + func.make_interval(0, 0, 0, 0, 0, 0, lease_duration_seconds),
                updated_at=func.now(),
            )
        )
        result = await self.db.execute(stmt)
        if result.rowcount == 1:
            return ReprocessingJobTransitionOutcome.APPLIED

        return await self._classify_owned_transition_failure(job_id, lease_token)

    async def _classify_owned_transition_failure(
        self,
        job_id: int,
        lease_token: str,
    ) -> ReprocessingJobTransitionOutcome:
        """Explain why an epoch-fenced write did not apply."""

        ownership = (
            await self.db.execute(
                select(
                    ReprocessingJob.status,
                    ReprocessingJob.lease_token,
                    (ReprocessingJob.lease_expires_at <= func.clock_timestamp()).label(
                        "lease_expired"
                    ),
                ).where(ReprocessingJob.id == job_id)
            )
        ).one_or_none()
        if ownership is None:
            return ReprocessingJobTransitionOutcome.NOT_FOUND
        if ownership.status != "PROCESSING":
            return ReprocessingJobTransitionOutcome.NOT_PROCESSING
        if ownership.lease_token != lease_token:
            return ReprocessingJobTransitionOutcome.TOKEN_MISMATCH
        if ownership.lease_expired:
            return ReprocessingJobTransitionOutcome.LEASE_EXPIRED
        return ReprocessingJobTransitionOutcome.RACED


def _over_limit_stale_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [row.id for row in stale_rows if row.attempt_count >= max_attempts]


def _resettable_stale_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [row.id for row in stale_rows if row.attempt_count < max_attempts]


def _claimed_reprocessing_job(row: Any) -> ClaimedReprocessingJob:
    return ClaimedReprocessingJob(
        id=int(row["id"]),
        job_type=str(row["job_type"]),
        payload=dict(row["payload"]),
        status=str(row["status"]),
        correlation_id=row.get("correlation_id"),
        correlation_missing_reason=row.get("correlation_missing_reason"),
        alternate_lookup_key=row.get("alternate_lookup_key"),
        attempt_count=int(row["attempt_count"]),
        created_at=cast(datetime, row["created_at"]),
        lease_token=str(row["lease_token"]),
        lease_expires_at=cast(datetime, row["lease_expires_at"]),
    )


def _effective_date_job_priority(
    job: ClaimedReprocessingJob,
) -> tuple[bool, str, datetime, int]:
    payload: dict[str, Any] = job.payload if isinstance(job.payload, dict) else {}
    raw_effective_date = payload.get("earliest_impacted_date")
    return (
        raw_effective_date is None,
        "" if raw_effective_date is None else str(raw_effective_date),
        cast(datetime, job.created_at),
        cast(int, job.id),
    )


def _stale_reprocessing_jobs_stmt():
    return (
        select(
            ReprocessingJob.id,
            ReprocessingJob.attempt_count,
            ReprocessingJob.job_type,
            ReprocessingJob.payload,
            ReprocessingJob.correlation_id,
            ReprocessingJob.correlation_missing_reason,
            ReprocessingJob.alternate_lookup_key,
            ReprocessingJob.lease_token,
        )
        .where(
            ReprocessingJob.status == "PROCESSING",
            ReprocessingJob.lease_expires_at <= func.clock_timestamp(),
        )
        .order_by(ReprocessingJob.lease_expires_at.asc(), ReprocessingJob.id.asc())
        .limit(POSTGRES_STATEMENT_ROW_LIMIT)
        .with_for_update(skip_locked=True)
    )


def _failed_stale_jobs_update_stmt(failed_job_ids: list[int]):
    return (
        _stale_jobs_update_stmt(failed_job_ids)
        .values(
            status="FAILED",
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            failure_reason="Stale processing timeout exceeded max attempts",
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _reset_stale_jobs_update_stmt(reset_job_ids: list[int]):
    return (
        _stale_jobs_update_stmt(reset_job_ids)
        .values(
            status="PENDING",
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _stale_jobs_update_stmt(job_ids: list[int]):
    return update(ReprocessingJob).where(
        ReprocessingJob.id.in_(job_ids),
        ReprocessingJob.status == "PROCESSING",
        ReprocessingJob.lease_expires_at <= func.clock_timestamp(),
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
