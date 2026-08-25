import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from portfolio_common.database_models import ReprocessingJob
from portfolio_common.reprocessing_job_repository import (
    ReprocessingJobRepository,
    ReprocessingJobTransitionOutcome,
)
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.valuation_orchestrator_service.app.core.reprocessing_worker import (
    ReprocessingWorker,
)
from src.services.valuation_orchestrator_service.app.core.reprocessing_worker_dependencies import (
    ReprocessingWorkerRepositoryFactory,
)

pytestmark = pytest.mark.asyncio


async def test_stale_security_replay_coalesces_with_newer_pending_job(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    stale_job = ReprocessingJob(
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S-STALE", "earliest_impacted_date": "2025-01-05"},
        status="PROCESSING",
        attempt_count=2,
        correlation_id="corr-stale-earliest",
        lease_owner="stale-security-worker",
        lease_token="1" * 32,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    pending_job = ReprocessingJob(
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S-STALE", "earliest_impacted_date": "2025-01-07"},
        status="PENDING",
        attempt_count=0,
        correlation_id="corr-pending-later",
    )
    async_db_session.add_all([stale_job, pending_job])
    await async_db_session.commit()

    recovered_count = await ReprocessingJobRepository(async_db_session).find_and_reset_stale_jobs(
        max_attempts=3
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert recovered_count == 1
    assert len(jobs) == 2
    assert jobs[0].status == "COMPLETE"
    assert jobs[0].failure_reason == (
        "Coalesced into pending security replay during stale recovery"
    )
    assert jobs[1].status == "PENDING"
    assert jobs[1].attempt_count == 2
    assert jobs[1].payload == {
        "security_id": "S-STALE",
        "earliest_impacted_date": "2025-01-05",
    }
    assert jobs[1].correlation_id == "corr-stale-earliest"


async def test_find_and_claim_jobs_prioritizes_oldest_pending_reset_watermarks(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN multiple pending RESET_WATERMARKS jobs for different securities
    WHEN the worker-facing claim path runs
    THEN jobs should be claimed by the oldest impacted date first.
    """
    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "S1", "earliest_impacted_date": "2025-01-07"},
                status="PENDING",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "S2", "earliest_impacted_date": "2025-01-05"},
                status="PENDING",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "S3", "earliest_impacted_date": "2025-01-06"},
                status="PENDING",
            ),
        ]
    )
    await async_db_session.commit()

    repository = ReprocessingJobRepository(async_db_session)

    claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=10)
    await async_db_session.commit()

    assert len(claimed) == 3
    assert claimed[0].payload["security_id"] == "S2"
    assert claimed[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert claimed[1].payload["security_id"] == "S3"
    assert claimed[2].payload["security_id"] == "S1"

    remaining_rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(remaining_rows) == 3
    assert {row.payload["security_id"] for row in remaining_rows} == {"S1", "S2", "S3"}


async def test_find_and_claim_jobs_keeps_malformed_payload_from_blocking_valid_sibling(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status)
            VALUES
              ('RESET_WATERMARKS', CAST('null' AS JSON), 'PENDING'),
              (
                'RESET_WATERMARKS',
                CAST('{"security_id":"S-VALID","earliest_impacted_date":"2025-01-05"}' AS JSON),
                'PENDING'
              )
            """
        )
    )
    await async_db_session.commit()

    claimed = await ReprocessingJobRepository(async_db_session).find_and_claim_jobs(
        "RESET_WATERMARKS",
        batch_size=2,
    )
    await async_db_session.commit()

    assert len(claimed) == 2
    assert any(job.payload is None for job in claimed)
    assert any(
        isinstance(job.payload, dict) and job.payload.get("security_id") == "S-VALID"
        for job in claimed
    )


async def test_find_and_claim_jobs_keeps_other_job_types_untouched(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN duplicate-looking payloads for a non-RESET_WATERMARKS job type
    WHEN the generic claim path runs
    THEN the repository should not apply reset-watermarks normalization logic.
    """
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status)
            VALUES
              (
                'OTHER_JOB',
                '{"security_id":"S1","earliest_impacted_date":"2025-01-07"}',
                'PENDING'
              ),
              (
                'OTHER_JOB',
                '{"security_id":"S1","earliest_impacted_date":"2025-01-05"}',
                'PENDING'
              )
            """
        )
    )
    await async_db_session.commit()

    repository = ReprocessingJobRepository(async_db_session)

    claimed = await repository.find_and_claim_jobs("OTHER_JOB", batch_size=10)
    await async_db_session.commit()

    assert len(claimed) == 2
    all_other_jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(ReprocessingJob.job_type == "OTHER_JOB")
            )
        )
        .scalars()
        .all()
    )
    assert len(all_other_jobs) == 2


async def test_pending_reset_watermarks_uniqueness_is_enforced_by_db(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN a pending RESET_WATERMARKS job already exists for a security
    WHEN a second pending RESET_WATERMARKS row for the same security is inserted directly
    THEN the database should reject it via the partial unique index.
    """
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status)
            VALUES (
              'RESET_WATERMARKS',
              '{"security_id":"S1","earliest_impacted_date":"2025-01-07"}',
              'PENDING'
            )
            """
        )
    )
    await async_db_session.commit()

    with pytest.raises(IntegrityError):
        await async_db_session.execute(
            text(
                """
                INSERT INTO reprocessing_jobs (job_type, payload, status)
                VALUES (
                  'RESET_WATERMARKS',
                  '{"security_id":"S1","earliest_impacted_date":"2025-01-05"}',
                  'PENDING'
                )
                """
            )
        )
        await async_db_session.commit()

    await async_db_session.rollback()


async def test_create_job_coalesces_pending_reset_watermarks_in_db(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN repeated repository create_job calls for the same security
    WHEN RESET_WATERMARKS work is created with a later then earlier impacted date
    THEN one pending row should remain and it should preserve the earliest date.
    """
    repository = ReprocessingJobRepository(async_db_session)

    first = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S1", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-late",
    )
    second = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S1", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-early",
    )
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(
                    ReprocessingJob.job_type == "RESET_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                    text("payload->>'security_id' = 'S1'"),
                )
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )

    assert first.id == second.id
    assert len(rows) == 1
    assert rows[0].payload["security_id"] == "S1"
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert rows[0].correlation_id == "corr-early"


async def test_create_job_backfills_missing_correlation_for_same_impacted_date(
    clean_db, async_db_session: AsyncSession
):
    repository = ReprocessingJobRepository(async_db_session)

    first = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S2", "earliest_impacted_date": "2025-01-05"},
        correlation_id=None,
    )
    second = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S2", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-fill",
    )
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(
                    ReprocessingJob.job_type == "RESET_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                    text("payload->>'security_id' = 'S2'"),
                )
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )

    assert first.id == second.id
    assert len(rows) == 1
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert rows[0].correlation_id == "corr-fill"
    assert rows[0].correlation_missing_reason is None
    assert rows[0].alternate_lookup_key is None


async def test_create_job_records_missing_correlation_diagnostics(
    clean_db, async_db_session: AsyncSession
):
    repository = ReprocessingJobRepository(async_db_session)

    job = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S9", "earliest_impacted_date": "2025-01-05"},
        correlation_id=None,
    )
    await async_db_session.commit()

    persisted = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(ReprocessingJob.id == job.id)
            )
        )
        .scalars()
        .one()
    )

    assert persisted.correlation_id is None
    assert persisted.correlation_missing_reason == "correlation_id_not_supplied"
    assert persisted.alternate_lookup_key == (
        "reprocessing_job|earliest_impacted_date=2025-01-05|job_type=RESET_WATERMARKS|"
        "security_id=S9"
    )


async def test_create_job_preserves_existing_correlation_when_earlier_date_has_none(
    clean_db, async_db_session: AsyncSession
):
    repository = ReprocessingJobRepository(async_db_session)

    first = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S3", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-existing",
    )
    second = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S3", "earliest_impacted_date": "2025-01-05"},
        correlation_id=None,
    )
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(
                    ReprocessingJob.job_type == "RESET_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                    text("payload->>'security_id' = 'S3'"),
                )
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )

    assert first.id == second.id
    assert len(rows) == 1
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert rows[0].correlation_id == "corr-existing"


async def test_find_and_reset_stale_jobs_does_not_overwrite_completed_rows(
    clean_db, async_db_session: AsyncSession
):
    job = ReprocessingJob(
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S4", "earliest_impacted_date": "2025-01-05"},
        status="PROCESSING",
        lease_owner="concurrent-completion-worker",
        lease_token="2" * 32,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    async_db_session.add(job)
    await async_db_session.flush()
    await async_db_session.execute(
        text(
            """
            UPDATE reprocessing_jobs
            SET lease_expires_at = clock_timestamp() - interval '20 minutes'
            WHERE id = :job_id
            """
        ),
        {"job_id": job.id},
    )
    await async_db_session.commit()

    concurrent_session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with concurrent_session_factory() as session:
        await session.execute(
            update(ReprocessingJob)
            .where(ReprocessingJob.id == job.id)
            .values(
                status="COMPLETE",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
            )
        )
        await session.commit()

    reset_count = await ReprocessingJobRepository(async_db_session).find_and_reset_stale_jobs(
        max_attempts=3
    )
    await async_db_session.commit()

    assert reset_count == 0

    async with concurrent_session_factory() as persisted_session:
        persisted = (
            (
                await persisted_session.execute(
                    select(ReprocessingJob).where(ReprocessingJob.id == job.id)
                )
            )
            .scalars()
            .one()
        )
    assert persisted.status == "COMPLETE"


async def test_find_and_claim_jobs_does_not_double_claim_under_concurrency(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add(
        ReprocessingJob(
            job_type="RESET_WATERMARKS",
            payload={"security_id": "S5", "earliest_impacted_date": "2025-01-05"},
            status="PENDING",
        )
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def claim_one():
        async with session_factory() as session:
            repository = ReprocessingJobRepository(session)
            claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1)
            await session.commit()
            return claimed

    first_claim, second_claim = await asyncio.gather(claim_one(), claim_one())
    all_claimed = [*first_claim, *second_claim]

    assert len(all_claimed) == 1
    assert len({job.id for job in all_claimed}) == 1

    persisted_rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(persisted_rows) == 1
    assert persisted_rows[0].status == "PROCESSING"
    assert persisted_rows[0].attempt_count == 1


async def test_expired_claim_is_recovered_reclaimed_and_fences_late_terminal_write(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    pending = ReprocessingJob(
        job_type="LEASE_LIFECYCLE_PROOF",
        payload={"scope": "reprocessing-lease-lifecycle"},
        status="PENDING",
    )
    async_db_session.add(pending)
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with session_factory() as first_session, first_session.begin():
        first_claim = (
            await ReprocessingJobRepository(first_session).find_and_claim_jobs(
                "LEASE_LIFECYCLE_PROOF",
                batch_size=1,
                lease_owner="first-reprocessing-worker",
                lease_duration_seconds=900,
            )
        )[0]

    original_expiry = first_claim.lease_expires_at
    async with session_factory() as renewal_session, renewal_session.begin():
        assert (
            await ReprocessingJobRepository(renewal_session).renew_lease(
                first_claim.id,
                lease_token=first_claim.lease_token,
                lease_duration_seconds=1800,
            )
            is ReprocessingJobTransitionOutcome.APPLIED
        )
    async with session_factory() as renewed_read_session:
        renewed = await renewed_read_session.get(ReprocessingJob, first_claim.id)
        assert renewed is not None
        assert renewed.lease_expires_at > original_expiry

    async with session_factory() as expiry_session, expiry_session.begin():
        await expiry_session.execute(
            update(ReprocessingJob)
            .where(ReprocessingJob.id == first_claim.id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )

    async with session_factory() as recovery_session, recovery_session.begin():
        assert (
            await ReprocessingJobRepository(recovery_session).find_and_reset_stale_jobs(
                max_attempts=3
            )
            == 1
        )

    async with session_factory() as second_session, second_session.begin():
        second_claim = (
            await ReprocessingJobRepository(second_session).find_and_claim_jobs(
                "LEASE_LIFECYCLE_PROOF",
                batch_size=1,
                lease_owner="second-reprocessing-worker",
                lease_duration_seconds=900,
            )
        )[0]

    assert second_claim.id == first_claim.id
    assert second_claim.attempt_count == 2
    assert second_claim.lease_token != first_claim.lease_token

    async with session_factory() as late_session, late_session.begin():
        assert (
            await ReprocessingJobRepository(late_session).update_job_status(
                first_claim.id,
                "COMPLETE",
                lease_token=first_claim.lease_token,
            )
            is ReprocessingJobTransitionOutcome.CLAIM_MISMATCH
        )

    async with session_factory() as current_session, current_session.begin():
        assert (
            await ReprocessingJobRepository(current_session).update_job_status(
                second_claim.id,
                "COMPLETE",
                lease_token=second_claim.lease_token,
            )
            is ReprocessingJobTransitionOutcome.APPLIED
        )

    async_db_session.expire_all()
    persisted = await async_db_session.get(ReprocessingJob, first_claim.id)
    assert persisted is not None
    assert persisted.status == "COMPLETE"
    assert persisted.attempt_count == 2
    assert persisted.lease_owner is None
    assert persisted.lease_token is None
    assert persisted.lease_expires_at is None


async def test_worker_database_failure_isolated_from_sibling_and_failed_in_fresh_session(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """A PostgreSQL-aborted job transaction cannot poison its sibling or failure write."""

    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": "FAIL-SECURITY",
                    "earliest_impacted_date": "2025-01-01",
                },
                status="PENDING",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": "PASS-SECURITY",
                    "earliest_impacted_date": "2025-01-02",
                },
                status="PENDING",
            ),
        ]
    )
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def session_provider():
        async with session_factory() as session:
            yield session

    class Valuations:
        async def find_portfolios_holding_security_on_date(self, *_args):
            return ["PORTFOLIO-1"]

        async def find_portfolios_first_holding_security_after_date(self, *_args):
            return []

    class PositionStates:
        def __init__(self, db):
            self.db = db

        async def update_watermarks_if_older(self, *, keys, new_watermark_date):
            del new_watermark_date
            if keys[0][1] == "FAIL-SECURITY":
                await self.db.execute(text("SELECT 1 / 0"))
            return len(keys)

    class FxRevaluations:
        async def claim_pending_jobs(self, *_args, **_kwargs):
            return []

    repositories = ReprocessingWorkerRepositoryFactory(
        reprocessing_job_repository_factory=ReprocessingJobRepository,
        position_state_repository_factory=PositionStates,
        valuation_repository_factory=lambda _db: Valuations(),
        fx_revaluation_repository_factory=lambda _db: FxRevaluations(),
    )
    worker = ReprocessingWorker(
        batch_size=2,
        session_provider=session_provider,
        repository_factory=repositories,
    )

    with patch(
        "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.observe_reprocessing_worker_jobs_failed"
    ) as observe_failed:
        await worker._process_batch()

    async_db_session.expire_all()
    persisted = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(ReprocessingJob.job_type == "RESET_WATERMARKS")
            )
        )
        .scalars()
        .all()
    )
    jobs_by_security = {job.payload["security_id"]: job for job in persisted}
    failed = jobs_by_security["FAIL-SECURITY"]
    succeeded = jobs_by_security["PASS-SECURITY"]
    assert failed.status == "FAILED"
    assert failed.attempt_count == 1
    assert "division by zero" in failed.failure_reason
    assert succeeded.status == "COMPLETE"
    assert succeeded.attempt_count == 1
    observe_failed.assert_called_once_with("RESET_WATERMARKS")
