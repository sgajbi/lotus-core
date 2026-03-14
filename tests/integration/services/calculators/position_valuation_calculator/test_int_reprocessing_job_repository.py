import asyncio

import pytest
from portfolio_common.database_models import ReprocessingJob
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


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
    )
    async_db_session.add(job)
    await async_db_session.flush()
    await async_db_session.execute(
        text(
            """
            UPDATE reprocessing_jobs
            SET updated_at = now() - interval '20 minutes'
            WHERE id = :job_id
            """
        ),
        {"job_id": job.id},
    )
    await async_db_session.commit()

    repository = ReprocessingJobRepository(async_db_session)
    original_execute = async_db_session.execute
    execute_count = 0
    concurrent_session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def execute_with_concurrent_completion(*args, **kwargs):
        nonlocal execute_count
        execute_count += 1
        if execute_count == 2:
            async with concurrent_session_factory() as session:
                await session.execute(
                    update(ReprocessingJob)
                    .where(ReprocessingJob.id == job.id)
                    .values(status="COMPLETE")
                )
                await session.commit()
        return await original_execute(*args, **kwargs)

    async_db_session.execute = execute_with_concurrent_completion
    reset_count = await repository.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)
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
