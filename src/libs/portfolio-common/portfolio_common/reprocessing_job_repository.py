# src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py
import logging
import unicodedata
import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Dict, Optional, cast

from sqlalchemy import Date, DateTime, String, bindparam, func, select, text, tuple_, update
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
from .reprocessing_payload_integrity import (
    LOCK_EFFECTIVE_DATED_REPLAY_IDENTITY,
    REPLAY_TEXT_TRIM_CHARS,
    UPSERT_PENDING_RESET_WATERMARKS,
    effective_dated_replay_identity_key,
    normalize_pending_reset_watermarks_duplicates,
    pending_replay_sibling_exists,
    quarantine_pending_fx_pair,
    quarantine_pending_reset_security,
)
from .utils import async_timed

logger = logging.getLogger(__name__)

EARLIEST_IMPACTED_DATE_JOB_TYPES = frozenset({"RESET_WATERMARKS", "RESET_FX_WATERMARKS"})
_STALE_FAILED_RESERVED_BINDS = 7
_STALE_RESET_RESERVED_BINDS = 5
_LEASE_OWNER_MAX_LENGTH = 128
_DEFAULT_LEASE_DURATION_SECONDS = 15 * 60
_OWNED_TRANSITION_STATUSES = frozenset({"COMPLETE", "FAILED"})
_STALE_RECOVERY_COHORT_LOCK_KEY = "lotus-core:reprocessing-stale-cohort"
_REPLAY_TEXT_TRIM_CHARS = REPLAY_TEXT_TRIM_CHARS


class ResetWatermarksStageOutcome(StrEnum):
    """Bounded persistence outcome for one reset-watermarks staging request."""

    CREATED = "created"
    COALESCED_PENDING = "coalesced_pending"


class ReprocessingJobTransitionOutcome(StrEnum):
    """Classify an exact owned transition without overstating lease authority."""

    APPLIED = "APPLIED"
    REQUEUED = "REQUEUED"
    COALESCED_PENDING = "COALESCED_PENDING"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    CLAIM_MISMATCH = "CLAIM_MISMATCH"
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
    payload: object
    status: str
    correlation_id: str | None
    correlation_missing_reason: str | None
    alternate_lookup_key: str | None
    attempt_count: int
    created_at: datetime
    lease_token: str
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class _EffectiveDatedReplayIdentity:
    """Validated identity needed to serialize one effective-dated replay family."""

    job_type: str
    identity_key: str
    payload: dict[str, Any]
    generated_at: datetime | None
    attempt_count: int
    correlation_id: str | None
    correlation_missing_reason: str | None
    alternate_lookup_key: str | None


def _claim_pending_jobs_query(job_type: str):
    if job_type in EARLIEST_IMPACTED_DATE_JOB_TYPES:
        return text(
            """
            WITH candidates AS MATERIALIZED (
                SELECT id
                FROM reprocessing_jobs
                WHERE status = 'PENDING'
                  AND job_type = :job_type
                  AND NOT (id = ANY(CAST(:excluded_job_ids AS BIGINT[])))
                ORDER BY (payload->>'earliest_impacted_date') ASC, created_at ASC, id ASC
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            UPDATE reprocessing_jobs AS target
            SET status = 'PROCESSING',
                updated_at = now(),
                last_attempted_at = now(),
                attempt_count = attempt_count + 1,
                lease_owner = :lease_owner,
                lease_token = :lease_token,
                lease_expires_at = clock_timestamp()
                    + make_interval(secs => :lease_duration_seconds)
            FROM candidates
            WHERE target.id = candidates.id
              AND target.status = 'PENDING'
              AND target.job_type = :job_type
            RETURNING target.*;
            """
        )

    return text(
        """
        WITH candidates AS MATERIALIZED (
            SELECT id
            FROM reprocessing_jobs
            WHERE status = 'PENDING'
              AND job_type = :job_type
              AND NOT (id = ANY(CAST(:excluded_job_ids AS BIGINT[])))
            ORDER BY created_at ASC, id ASC
            LIMIT :batch_size
            FOR UPDATE SKIP LOCKED
        )
        UPDATE reprocessing_jobs AS target
        SET status = 'PROCESSING',
            updated_at = now(),
            last_attempted_at = now(),
            attempt_count = attempt_count + 1,
            lease_owner = :lease_owner,
            lease_token = :lease_token,
            lease_expires_at = clock_timestamp()
                + make_interval(secs => :lease_duration_seconds)
        FROM candidates
        WHERE target.id = candidates.id
          AND target.status = 'PENDING'
          AND target.job_type = :job_type
        RETURNING target.*;
        """
    )


class ReprocessingJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._default_lease_owner = f"reprocessing-repository-{uuid.uuid4().hex}"

    async def normalize_pending_reset_watermarks_duplicates(self) -> int:
        """Coalesce valid historical RESET_WATERMARKS work by earliest date.

        Scalar identities are failed before canonical string identities are rewritten.
        This ordering prevents a legacy numeric/string collision from violating the
        pending-work uniqueness fence and blocking claims for the entire queue.

        Return the number of redundant valid rows removed.
        """
        deleted_count = await normalize_pending_reset_watermarks_duplicates(self.db)
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
        generated_at: datetime,
        correlation_id: str | None,
        correlation_missing_reason: str | None,
        alternate_lookup_key: str | None,
        attempt_count: int = 0,
    ) -> None:
        """Quarantine malformed pair work, then coalesce one valid pending FX replay."""

        if not isinstance(generated_at, datetime):
            raise TypeError("FX replay generated_at must be a datetime")
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("FX replay generated_at must be timezone-aware")

        staging_payload = {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "content_hash": content_hash,
        }
        from_currency = _required_replay_payload_text(staging_payload, "from_currency")
        to_currency = _required_replay_payload_text(staging_payload, "to_currency")
        content_hash = _required_replay_payload_text(staging_payload, "content_hash")

        await self._lock_effective_dated_replay_identity(
            effective_dated_replay_identity_key(
                "RESET_FX_WATERMARKS",
                from_currency,
                to_currency,
            )
        )

        quarantined_earliest_date = await self._quarantine_malformed_pending_fx_pair(
            from_currency=from_currency,
            to_currency=to_currency,
        )
        if quarantined_earliest_date is not None:
            earliest_impacted_date = min(
                earliest_impacted_date,
                quarantined_earliest_date,
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
                    'generated_at', :generated_at_text
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
                        THEN :generated_at_text
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
            bindparam("generated_at", type_=DateTime(timezone=True)),
            bindparam("generated_at_text", type_=String()),
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
                "generated_at_text": generated_at.isoformat(),
                "attempt_count": attempt_count,
                "correlation_id": correlation_id,
                "correlation_missing_reason": correlation_missing_reason,
                "alternate_lookup_key": alternate_lookup_key,
            },
        )

    async def _quarantine_malformed_pending_fx_pair(
        self,
        *,
        from_currency: str,
        to_currency: str,
    ) -> date | None:
        """Validate predecessor pair work with the application grammar before coalescing."""
        return await quarantine_pending_fx_pair(
            self.db,
            from_currency=from_currency,
            to_currency=to_currency,
            validate=lambda payload: _validated_effective_dated_replay_identity(
                job_type="RESET_FX_WATERMARKS",
                payload=payload,
                attempt_count=0,
                correlation_id=None,
                correlation_missing_reason=None,
                alternate_lookup_key=None,
            ),
            parse_earliest_date=_parse_replay_earliest_date,
        )

    async def _quarantine_malformed_pending_reset_watermarks(
        self,
        *,
        security_id: str,
    ) -> date | None:
        """Quarantine malformed retained security replay before date-bearing SQL."""
        return await quarantine_pending_reset_security(
            self.db,
            security_id=security_id,
            validate=lambda payload: _validated_effective_dated_replay_identity(
                job_type="RESET_WATERMARKS",
                payload=payload,
                attempt_count=0,
                correlation_id=None,
                correlation_missing_reason=None,
                alternate_lookup_key=None,
            ),
            parse_earliest_date=_parse_replay_earliest_date,
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
        security_id = _required_replay_payload_text(
            {"security_id": security_id},
            "security_id",
        )
        await self._lock_effective_dated_replay_identity(
            effective_dated_replay_identity_key("RESET_WATERMARKS", security_id)
        )
        quarantined_earliest_date = await self._quarantine_malformed_pending_reset_watermarks(
            security_id=security_id,
        )
        if quarantined_earliest_date is not None:
            earliest_impacted_date = min(
                earliest_impacted_date,
                quarantined_earliest_date,
            )
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
        result = await self.db.execute(
            UPSERT_PENDING_RESET_WATERMARKS,
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

    async def lock_reset_watermarks_replay_identities(
        self,
        security_ids: Collection[str],
    ) -> None:
        """Pre-lock a replay batch in the global identity order for this transaction."""

        await self._lock_effective_dated_replay_identities(
            effective_dated_replay_identity_key("RESET_WATERMARKS", security_id)
            for security_id in security_ids
        )

    @async_timed(repository="ReprocessingJobRepository", method="find_and_claim_jobs")
    async def find_and_claim_jobs(
        self,
        job_type: str,
        batch_size: int,
        *,
        lease_owner: str | None = None,
        lease_duration_seconds: int = _DEFAULT_LEASE_DURATION_SECONDS,
        excluded_job_ids: Collection[int] = (),
        normalize_reset_watermark_duplicates: bool = True,
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

        if job_type == "RESET_WATERMARKS" and normalize_reset_watermark_duplicates:
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
                "excluded_job_ids": sorted(set(excluded_job_ids)),
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

        stale_rows = await self._claim_stale_job_cohort(max_attempts=max_attempts)
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

    async def _claim_stale_job_cohort(self, *, max_attempts: int) -> list[Any]:
        """Claim one disjoint cohort after taking replay identity locks in global order."""

        cursor: tuple[datetime, int] | None = None
        while stale_rows := await self._find_stale_job_rows(after=cursor):
            savepoint = self.db.begin_nested()
            await savepoint.start()
            savepoint_closed = False
            cohort_lock_acquired = False
            cohort_lock_released = False
            try:
                identity_keys = []
                for row in stale_rows:
                    try:
                        identity = _retryable_stale_replay_identity(
                            row,
                            max_attempts=max_attempts,
                        )
                    except (KeyError, TypeError, ValueError):
                        continue
                    if identity is not None:
                        identity_keys.append(identity.identity_key)
                await self._lock_effective_dated_replay_identities(identity_keys)
                await self._lock_stale_recovery_cohort_claim()
                cohort_lock_acquired = True
                try:
                    try:
                        claimed_rows = list(
                            (
                                await self.db.execute(
                                    _stale_reprocessing_jobs_stmt(
                                        job_ids=[int(row.id) for row in stale_rows],
                                        lock_rows=True,
                                    )
                                )
                            ).all()
                        )
                    except BaseException:
                        # A failed statement aborts the savepoint. Roll it back
                        # before releasing the session-level advisory lock so the
                        # unlock can execute on a usable transaction.
                        await savepoint.rollback()
                        savepoint_closed = True
                        raise
                finally:
                    await self._unlock_stale_recovery_cohort_claim()
                    cohort_lock_released = True
                if claimed_rows:
                    await savepoint.commit()
                    savepoint_closed = True
                    return claimed_rows
                await savepoint.rollback()
                savepoint_closed = True
            except BaseException:
                if not savepoint_closed:
                    await savepoint.rollback()
                    savepoint_closed = True
                if cohort_lock_acquired and not cohort_lock_released:
                    await self._unlock_stale_recovery_cohort_claim()
                raise
            last_row = stale_rows[-1]
            cursor = (cast(datetime, last_row.lease_expires_at), int(last_row.id))
        return []

    async def _lock_stale_recovery_cohort_claim(self) -> None:
        """Serialize the bounded row-lock statement without holding a transaction lock.

        ``FOR UPDATE SKIP LOCKED`` can interleave row-by-row when two recovery
        sessions start together, producing arbitrary sub-cohorts (for example
        110/890 instead of the intended 1/1000 split). A session-level advisory
        lock covers only the claim statement; row locks remain transaction-owned,
        so concurrent callers still receive disjoint cohorts without a barrier
        deadlock while waiting for the outer transaction to commit.
        """

        await self.db.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": _STALE_RECOVERY_COHORT_LOCK_KEY},
        )

    async def _unlock_stale_recovery_cohort_claim(self) -> None:
        unlocked = (
            await self.db.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
                {"lock_key": _STALE_RECOVERY_COHORT_LOCK_KEY},
            )
        ).scalar_one()
        if unlocked is not True:
            raise RuntimeError("stale recovery cohort advisory lock was not held")

    async def _find_stale_job_rows(
        self,
        *,
        after: tuple[datetime, int] | None = None,
    ) -> list[Any]:
        return list((await self.db.execute(_stale_reprocessing_jobs_stmt(after=after))).all())

    async def _recover_retryable_stale_coalesced_jobs(
        self,
        stale_rows: list[Any],
        *,
        max_attempts: int,
    ) -> tuple[set[int], int]:
        handled_job_ids: set[int] = set()
        recovered_count = 0
        candidates: list[tuple[Any, _EffectiveDatedReplayIdentity]] = []
        for row in stale_rows:
            try:
                identity = _retryable_stale_replay_identity(
                    row,
                    max_attempts=max_attempts,
                )
            except (KeyError, TypeError, ValueError):
                handled_job_ids.add(int(row.id))
                await self._fail_malformed_stale_replay(row)
                continue
            if identity is None:
                continue
            handled_job_ids.add(int(row.id))
            candidates.append((row, identity))

        for row, candidate_identity in candidates:
            try:
                locked_row = await self._lock_stale_effective_dated_job(
                    job_id=int(row.id),
                    lease_token=row.lease_token,
                )
                if locked_row is None:
                    continue
                identity = _validated_effective_dated_replay_identity(
                    job_type=str(locked_row.job_type),
                    payload=locked_row.payload,
                    attempt_count=int(locked_row.attempt_count),
                    correlation_id=locked_row.correlation_id,
                    correlation_missing_reason=locked_row.correlation_missing_reason,
                    alternate_lookup_key=locked_row.alternate_lookup_key,
                )
                if identity.identity_key != candidate_identity.identity_key:
                    continue
                payload = identity.payload
                if identity.job_type == "RESET_FX_WATERMARKS":
                    await self.stage_pending_fx_revaluation_job(
                        from_currency=payload["from_currency"],
                        to_currency=payload["to_currency"],
                        earliest_impacted_date=date.fromisoformat(
                            payload["earliest_impacted_date"]
                        ),
                        content_hash=payload["content_hash"],
                        generated_at=cast(datetime, identity.generated_at),
                        correlation_id=identity.correlation_id,
                        correlation_missing_reason=identity.correlation_missing_reason,
                        alternate_lookup_key=identity.alternate_lookup_key,
                        attempt_count=identity.attempt_count,
                    )
                    completion_reason = "Coalesced into pending FX replay during stale recovery"
                else:
                    await self.create_job(
                        identity.job_type,
                        payload,
                        correlation_id=identity.correlation_id,
                        attempt_count=identity.attempt_count,
                    )
                    completion_reason = (
                        "Coalesced into pending security replay during stale recovery"
                    )
            except (KeyError, TypeError, ValueError):
                await self._fail_malformed_stale_replay(row)
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
                recovered_count += 1
        return handled_job_ids, recovered_count

    async def _fail_malformed_stale_replay(self, row: Any) -> None:
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
        await self.db.execute(
            _stale_jobs_update_stmt([row.id]).values(
                status="FAILED",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                failure_reason="Malformed effective-dated replay during stale recovery",
                updated_at=func.now(),
            )
        )

    async def _lock_stale_effective_dated_job(
        self,
        *,
        job_id: int,
        lease_token: str | None,
    ) -> Any | None:
        """Revalidate and row-lock one stale lease after its identity lock is held."""

        return (
            await self.db.execute(
                select(
                    ReprocessingJob.job_type,
                    ReprocessingJob.payload,
                    ReprocessingJob.attempt_count,
                    ReprocessingJob.correlation_id,
                    ReprocessingJob.correlation_missing_reason,
                    ReprocessingJob.alternate_lookup_key,
                )
                .where(
                    ReprocessingJob.id == job_id,
                    ReprocessingJob.status == "PROCESSING",
                    ReprocessingJob.lease_token == lease_token,
                    ReprocessingJob.lease_expires_at <= func.clock_timestamp(),
                )
                .with_for_update()
            )
        ).one_or_none()

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

    @async_timed(
        repository="ReprocessingJobRepository",
        method="requeue_owned_effective_dated_job",
    )
    async def requeue_owned_effective_dated_job(
        self,
        job_id: int,
        *,
        lease_token: str,
    ) -> ReprocessingJobTransitionOutcome:
        """Requeue a live claim and preserve any pending sibling's earliest replay boundary."""

        if not lease_token:
            raise ValueError("reprocessing lease token is required")
        identity = await self._effective_dated_replay_identity(job_id)
        if identity is None:
            return ReprocessingJobTransitionOutcome.NOT_FOUND

        await self._lock_effective_dated_replay_identity(identity.identity_key)
        if not await self._lock_live_owned_job(job_id=job_id, lease_token=lease_token):
            return await self._classify_owned_transition_failure(job_id, lease_token)

        if not await self._pending_replay_sibling_exists(
            job_id=job_id,
            identity=identity,
        ):
            outcome = await self._apply_owned_transition(
                job_id,
                "PENDING",
                lease_token=lease_token,
            )
            return (
                ReprocessingJobTransitionOutcome.REQUEUED
                if outcome is ReprocessingJobTransitionOutcome.APPLIED
                else outcome
            )

        savepoint = self.db.begin_nested()
        await savepoint.start()
        try:
            await self._coalesce_pending_replay(identity)
            outcome = await self._apply_owned_transition(
                job_id,
                "COMPLETE",
                lease_token=lease_token,
            )
            if outcome is not ReprocessingJobTransitionOutcome.APPLIED:
                await savepoint.rollback()
                return outcome
            await savepoint.commit()
        except Exception:
            await savepoint.rollback()
            raise
        return ReprocessingJobTransitionOutcome.COALESCED_PENDING

    async def _effective_dated_replay_identity(
        self,
        job_id: int,
    ) -> _EffectiveDatedReplayIdentity | None:
        row = (
            await self.db.execute(
                select(
                    ReprocessingJob.job_type,
                    ReprocessingJob.payload,
                    ReprocessingJob.attempt_count,
                    ReprocessingJob.correlation_id,
                    ReprocessingJob.correlation_missing_reason,
                    ReprocessingJob.alternate_lookup_key,
                ).where(ReprocessingJob.id == job_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return _validated_effective_dated_replay_identity(
            job_type=str(row.job_type),
            payload=row.payload,
            attempt_count=int(row.attempt_count),
            correlation_id=row.correlation_id,
            correlation_missing_reason=row.correlation_missing_reason,
            alternate_lookup_key=row.alternate_lookup_key,
        )

    async def _lock_effective_dated_replay_identity(self, identity_key: str) -> None:
        await self.db.execute(
            LOCK_EFFECTIVE_DATED_REPLAY_IDENTITY,
            {"identity_key": identity_key},
        )

    async def _lock_effective_dated_replay_identities(
        self,
        identity_keys: Iterable[str],
    ) -> None:
        for identity_key in sorted(set(identity_keys)):
            await self._lock_effective_dated_replay_identity(identity_key)

    async def _lock_live_owned_job(self, *, job_id: int, lease_token: str) -> bool:
        owned_job_id = (
            await self.db.execute(
                select(ReprocessingJob.id)
                .where(
                    ReprocessingJob.id == job_id,
                    ReprocessingJob.status == "PROCESSING",
                    ReprocessingJob.lease_token == lease_token,
                    ReprocessingJob.lease_expires_at > func.clock_timestamp(),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        return owned_job_id is not None

    async def _pending_replay_sibling_exists(
        self,
        *,
        job_id: int,
        identity: _EffectiveDatedReplayIdentity,
    ) -> bool:
        return await pending_replay_sibling_exists(
            self.db,
            job_id=job_id,
            job_type=identity.job_type,
            payload=identity.payload,
        )

    async def _coalesce_pending_replay(self, identity: _EffectiveDatedReplayIdentity) -> None:
        payload = identity.payload
        earliest_impacted_date = date.fromisoformat(payload["earliest_impacted_date"])
        if identity.job_type == "RESET_WATERMARKS":
            await self.stage_reset_watermarks_job(
                security_id=payload["security_id"],
                earliest_impacted_date=earliest_impacted_date,
                correlation_id=identity.correlation_id,
                attempt_count=identity.attempt_count,
            )
            return
        await self.stage_pending_fx_revaluation_job(
            from_currency=payload["from_currency"],
            to_currency=payload["to_currency"],
            earliest_impacted_date=earliest_impacted_date,
            content_hash=payload["content_hash"],
            generated_at=cast(datetime, identity.generated_at),
            correlation_id=identity.correlation_id,
            correlation_missing_reason=identity.correlation_missing_reason,
            alternate_lookup_key=identity.alternate_lookup_key,
            attempt_count=identity.attempt_count,
        )

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
        return await self._apply_owned_transition(
            job_id,
            status,
            lease_token=lease_token,
            failure_reason=failure_reason,
        )

    async def _apply_owned_transition(
        self,
        job_id: int,
        status: str,
        *,
        lease_token: str,
        failure_reason: str | None = None,
    ) -> ReprocessingJobTransitionOutcome:
        stmt = (
            update(ReprocessingJob)
            .where(
                ReprocessingJob.id == job_id,
                ReprocessingJob.status == "PROCESSING",
                ReprocessingJob.lease_token == lease_token,
                ReprocessingJob.lease_expires_at > func.clock_timestamp(),
            )
            .values(
                status=status,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=func.now(),
            )
        )
        if failure_reason is not None:
            stmt = stmt.values(failure_reason=failure_reason)
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

    async def get_lease_remaining_seconds(
        self,
        job_id: int,
        *,
        lease_token: str,
    ) -> float | None:
        """Read the live lease budget from PostgreSQL's clock for local scheduling."""

        row = (
            await self.db.execute(
                select(
                    (
                        func.extract(
                            "epoch",
                            ReprocessingJob.lease_expires_at - func.clock_timestamp(),
                        )
                    ).label("lease_remaining_seconds")
                ).where(
                    ReprocessingJob.id == job_id,
                    ReprocessingJob.status == "PROCESSING",
                    ReprocessingJob.lease_token == lease_token,
                    ReprocessingJob.lease_expires_at > func.clock_timestamp(),
                )
            )
        ).one_or_none()
        if row is None or row.lease_remaining_seconds is None:
            return None
        return float(row.lease_remaining_seconds)

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
            return ReprocessingJobTransitionOutcome.CLAIM_MISMATCH
        if ownership.lease_expired:
            return ReprocessingJobTransitionOutcome.LEASE_EXPIRED
        return ReprocessingJobTransitionOutcome.RACED


def _retryable_stale_replay_identity(
    row: Any,
    *,
    max_attempts: int,
) -> _EffectiveDatedReplayIdentity | None:
    if row.job_type not in EARLIEST_IMPACTED_DATE_JOB_TYPES:
        return None
    if int(row.attempt_count) >= max_attempts:
        return None
    return _validated_effective_dated_replay_identity(
        job_type=str(row.job_type),
        payload=row.payload,
        attempt_count=int(row.attempt_count),
        correlation_id=row.correlation_id,
        correlation_missing_reason=row.correlation_missing_reason,
        alternate_lookup_key=row.alternate_lookup_key,
    )


def _validated_effective_dated_replay_identity(
    *,
    job_type: str,
    payload: Any,
    attempt_count: int,
    correlation_id: str | None,
    correlation_missing_reason: str | None,
    alternate_lookup_key: str | None,
) -> _EffectiveDatedReplayIdentity:
    if job_type not in EARLIEST_IMPACTED_DATE_JOB_TYPES or not isinstance(payload, dict):
        raise ValueError("owned requeue requires a supported effective-dated replay payload")
    earliest_impacted_date = _required_replay_payload_text(payload, "earliest_impacted_date")
    date.fromisoformat(earliest_impacted_date)
    components: tuple[str, ...]
    generated_at: datetime | None = None
    if job_type == "RESET_WATERMARKS":
        components = (_required_replay_payload_text(payload, "security_id"),)
    else:
        components = (
            _required_replay_payload_text(payload, "from_currency"),
            _required_replay_payload_text(payload, "to_currency"),
        )
        _required_replay_payload_text(payload, "content_hash")
        generated_at = datetime.fromisoformat(
            _required_replay_payload_text(payload, "generated_at")
        )
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("FX replay generated_at must be timezone-aware")
    return _EffectiveDatedReplayIdentity(
        job_type=job_type,
        identity_key=effective_dated_replay_identity_key(job_type, *components),
        payload=cast(dict[str, Any], payload),
        generated_at=generated_at,
        attempt_count=attempt_count,
        correlation_id=correlation_id,
        correlation_missing_reason=correlation_missing_reason,
        alternate_lookup_key=alternate_lookup_key,
    )


def _required_replay_payload_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"effective-dated replay payload requires {key}")
    if value != value.strip():
        raise ValueError(f"effective-dated replay payload {key} must be normalized")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"effective-dated replay payload {key} contains a control character")
    return value


def _parse_replay_earliest_date(payload: object) -> date | None:
    try:
        if not isinstance(payload, dict):
            return None
        return date.fromisoformat(_required_replay_payload_text(payload, "earliest_impacted_date"))
    except (TypeError, ValueError):
        return None


def _over_limit_stale_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [row.id for row in stale_rows if row.attempt_count >= max_attempts]


def _resettable_stale_job_ids(stale_rows: list[Any], max_attempts: int) -> list[int]:
    return [row.id for row in stale_rows if row.attempt_count < max_attempts]


def _claimed_reprocessing_job(row: Any) -> ClaimedReprocessingJob:
    return ClaimedReprocessingJob(
        id=int(row["id"]),
        job_type=str(row["job_type"]),
        # Preserve database JSON as-is so malformed legacy payloads are rejected
        # inside their independently committed job execution, not while mapping
        # the entire claim result.
        payload=row["payload"],
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


def _stale_reprocessing_jobs_stmt(
    *,
    after: tuple[datetime, int] | None = None,
    job_ids: Collection[int] | None = None,
    lock_rows: bool = False,
):
    statement = (
        select(
            ReprocessingJob.id,
            ReprocessingJob.attempt_count,
            ReprocessingJob.job_type,
            ReprocessingJob.payload,
            ReprocessingJob.correlation_id,
            ReprocessingJob.correlation_missing_reason,
            ReprocessingJob.alternate_lookup_key,
            ReprocessingJob.lease_token,
            ReprocessingJob.lease_expires_at,
        )
        .where(
            ReprocessingJob.status == "PROCESSING",
            ReprocessingJob.lease_expires_at <= func.clock_timestamp(),
        )
        .order_by(ReprocessingJob.lease_expires_at.asc(), ReprocessingJob.id.asc())
        .limit(POSTGRES_STATEMENT_ROW_LIMIT)
    )
    if after is not None:
        statement = statement.where(
            tuple_(ReprocessingJob.lease_expires_at, ReprocessingJob.id) > after
        )
    if job_ids is not None:
        statement = statement.where(ReprocessingJob.id.in_(sorted(set(job_ids))))
    if lock_rows:
        statement = statement.with_for_update(skip_locked=True)
    return statement


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
