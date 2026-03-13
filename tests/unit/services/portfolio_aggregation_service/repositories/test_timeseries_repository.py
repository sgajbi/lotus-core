from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_aggregation_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.fetchall.return_value = []
    result.all.return_value = []
    result.rowcount = 1
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> TimeseriesRepository:
    return TimeseriesRepository(mock_db_session)


async def test_find_and_claim_eligible_jobs_prior_day_gate_does_not_require_current_epoch_match(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.find_and_claim_eligible_jobs(batch_size=5)

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert (
        "portfolio_timeseries.date = portfolio_aggregation_jobs.aggregation_date -"
        in compiled_query
    )
    assert "portfolio_timeseries.epoch =" not in compiled_query


async def test_find_and_claim_eligible_jobs_first_day_gate_is_directly_correlated(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.find_and_claim_eligible_jobs(batch_size=5)

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert (
        "portfolio_aggregation_jobs_1.portfolio_id = portfolio_aggregation_jobs.portfolio_id"
        in compiled_query
    )
    assert "FROM portfolio_timeseries, portfolio_aggregation_jobs" not in compiled_query


async def test_find_and_claim_eligible_jobs_completeness_gate_stays_correlated(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.find_and_claim_eligible_jobs(batch_size=5)

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "FROM daily_position_snapshots, portfolio_aggregation_jobs" not in compiled_query
    assert "FROM position_timeseries, portfolio_aggregation_jobs" not in compiled_query


async def test_find_and_reset_stale_jobs_refreshes_updated_at(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    stale_result = MagicMock()
    stale_result.all.return_value = [MagicMock(id=1, attempt_count=1)]
    mock_db_session.execute.side_effect = [stale_result, mock_db_session.execute.return_value]

    await repository.find_and_reset_stale_jobs()

    executed_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "UPDATE portfolio_aggregation_jobs" in compiled_query
    assert "SET status='PENDING'" in compiled_query
    assert "updated_at=now()" in compiled_query


async def test_find_and_claim_eligible_jobs_increments_attempt_count(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    eligible_result = MagicMock()
    eligible_result.fetchall.return_value = [(1,)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [
        MagicMock(portfolio_id="P1", aggregation_date=date(2025, 1, 1))
    ]
    mock_db_session.execute.side_effect = [eligible_result, claimed_result]

    await repository.find_and_claim_eligible_jobs(batch_size=5)

    executed_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "UPDATE portfolio_aggregation_jobs" in compiled_query
    assert "SET status='PROCESSING'" in compiled_query
    assert "attempt_count=(portfolio_aggregation_jobs.attempt_count + 1)" in compiled_query
