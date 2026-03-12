import pytest
from portfolio_common.database_models import ReprocessingJob
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
    )
    second = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S1", "earliest_impacted_date": "2025-01-05"},
    )
    await async_db_session.commit()

    rows = (
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

    assert first.id == second.id
    assert len(rows) == 1
    assert rows[0].payload["security_id"] == "S1"
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"
