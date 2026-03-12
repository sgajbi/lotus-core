from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import ReprocessingJob
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> ReprocessingJobRepository:
    return ReprocessingJobRepository(db=mock_db_session)


async def test_find_and_claim_jobs_uses_atomic_skip_locked_update(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 0
    mock_db_session.execute.side_effect = [normalize_result, mock_result]

    await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=25)

    assert mock_db_session.execute.await_count == 2
    query = mock_db_session.execute.await_args_list[1].args[0]
    params = mock_db_session.execute.await_args_list[1].args[1]
    query_text = str(query)

    assert "UPDATE reprocessing_jobs" in query_text
    assert "FOR UPDATE SKIP LOCKED" in query_text
    assert "RETURNING *" in query_text
    assert params["job_type"] == "RESET_WATERMARKS"
    assert params["batch_size"] == 25
    assert "(payload->>'earliest_impacted_date')::date ASC" in query_text


async def test_find_and_claim_jobs_uses_default_created_at_order_for_other_job_types(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    await repository.find_and_claim_jobs("OTHER_JOB", batch_size=10)

    query = mock_db_session.execute.await_args.args[0]
    query_text = str(query)

    assert "ORDER BY created_at ASC, id ASC" in query_text
    assert "(payload->>'earliest_impacted_date')::date ASC" not in query_text


async def test_normalize_pending_reset_watermarks_duplicates_uses_set_based_cleanup(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 2
    mock_db_session.execute.return_value = mock_result

    deleted_count = await repository.normalize_pending_reset_watermarks_duplicates()

    assert deleted_count == 2
    stmt = mock_db_session.execute.await_args.args[0]
    stmt_text = str(stmt)
    assert "WITH ranked AS" in stmt_text
    assert "DELETE FROM reprocessing_jobs" in stmt_text
    assert "jsonb_set" in stmt_text


async def test_find_and_claim_jobs_normalizes_reset_watermarks_duplicates_before_claim(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 1
    claim_result = MagicMock()
    claim_result.mappings.return_value.all.return_value = []
    mock_db_session.execute.side_effect = [normalize_result, claim_result]

    await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=10)

    assert mock_db_session.execute.await_count == 2
    normalize_stmt = mock_db_session.execute.await_args_list[0].args[0]
    claim_stmt = mock_db_session.execute.await_args_list[1].args[0]
    assert "WITH ranked AS" in str(normalize_stmt)
    assert "UPDATE reprocessing_jobs" in str(claim_stmt)


async def test_find_and_claim_jobs_maps_rows_to_models(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": 10,
            "job_type": "RESET_WATERMARKS",
            "payload": {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
            "status": "PROCESSING",
            "attempt_count": 1,
            "last_attempted_at": None,
            "failure_reason": None,
            "created_at": None,
            "updated_at": None,
        }
    ]
    mock_db_session.execute.return_value = mock_result

    claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1)

    assert len(claimed) == 1
    assert claimed[0].id == 10
    assert claimed[0].status == "PROCESSING"


async def test_find_and_claim_jobs_returns_reset_watermarks_in_priority_order(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 0
    claim_result = MagicMock()
    claim_result.mappings.return_value.all.return_value = [
        {
            "id": 30,
            "job_type": "RESET_WATERMARKS",
            "payload": {"security_id": "S1", "earliest_impacted_date": "2025-01-07"},
            "status": "PROCESSING",
            "attempt_count": 1,
            "last_attempted_at": None,
            "failure_reason": None,
            "created_at": None,
            "updated_at": None,
        },
        {
            "id": 20,
            "job_type": "RESET_WATERMARKS",
            "payload": {"security_id": "S2", "earliest_impacted_date": "2025-01-05"},
            "status": "PROCESSING",
            "attempt_count": 1,
            "last_attempted_at": None,
            "failure_reason": None,
            "created_at": None,
            "updated_at": None,
        },
    ]
    mock_db_session.execute.side_effect = [normalize_result, claim_result]

    claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=10)

    assert [job.payload["security_id"] for job in claimed] == ["S2", "S1"]


async def test_find_and_reset_stale_jobs_resets_processing_rows(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value = [10, 11]
    mock_update_result = MagicMock()
    mock_update_result.rowcount = 2
    mock_db_session.execute.side_effect = [mock_select_result, mock_update_result]

    reset_count = await repository.find_and_reset_stale_jobs(timeout_minutes=30)

    assert reset_count == 2
    assert mock_db_session.execute.await_count == 2
    select_stmt = mock_db_session.execute.await_args_list[0].args[0]
    update_stmt = mock_db_session.execute.await_args_list[1].args[0]
    assert "SELECT reprocessing_jobs.id" in str(select_stmt)
    assert "UPDATE reprocessing_jobs SET status=:status" in str(update_stmt)


async def test_find_and_reset_stale_jobs_is_noop_when_nothing_stale(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value = []
    mock_db_session.execute.return_value = mock_select_result

    reset_count = await repository.find_and_reset_stale_jobs(timeout_minutes=30)

    assert reset_count == 0
    assert mock_db_session.execute.await_count == 1


async def test_create_job_coalesces_pending_reset_watermarks_job(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    upsert_result = MagicMock()
    upsert_result.mappings.return_value.one.return_value = {
        "id": 10,
        "job_type": "RESET_WATERMARKS",
        "payload": {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
        "status": "PENDING",
        "attempt_count": 0,
        "last_attempted_at": None,
        "failure_reason": None,
        "created_at": None,
        "updated_at": None,
    }
    mock_db_session.execute.return_value = upsert_result

    result = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "AAPL", "earliest_impacted_date": "2025-01-07"},
    )

    assert result.id == 10
    assert result.payload["earliest_impacted_date"] == "2025-01-05"
    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_awaited()
    assert mock_db_session.execute.await_count == 1


async def test_create_job_updates_pending_reset_watermarks_job_to_earliest_date(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    upsert_result = MagicMock()
    upsert_result.mappings.return_value.one.return_value = {
        "id": 10,
        "job_type": "RESET_WATERMARKS",
        "payload": {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
        "status": "PENDING",
        "attempt_count": 0,
        "last_attempted_at": None,
        "failure_reason": None,
        "created_at": None,
        "updated_at": None,
    }
    mock_db_session.execute.return_value = upsert_result

    result = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
    )

    assert result.payload["earliest_impacted_date"] == "2025-01-05"
    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_awaited()
    assert mock_db_session.execute.await_count == 1
