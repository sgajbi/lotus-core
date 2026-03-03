from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository


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
    mock_db_session.execute.return_value = mock_result

    await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=25)

    mock_db_session.execute.assert_awaited_once()
    query = mock_db_session.execute.await_args.args[0]
    params = mock_db_session.execute.await_args.args[1]
    query_text = str(query)

    assert "UPDATE reprocessing_jobs" in query_text
    assert "FOR UPDATE SKIP LOCKED" in query_text
    assert "RETURNING *" in query_text
    assert params["job_type"] == "RESET_WATERMARKS"
    assert params["batch_size"] == 25


async def test_find_and_claim_jobs_maps_rows_to_models(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": 10,
            "job_type": "RESET_WATERMARKS",
            "payload": {"security_id": "AAPL"},
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
