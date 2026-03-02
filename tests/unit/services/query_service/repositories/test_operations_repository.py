from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.operations_repository import (
    OperationsRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> OperationsRepository:
    return OperationsRepository(mock_db_session)


def mock_execute_scalar_one_or_none(mock_db_session: AsyncMock, value):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    mock_db_session.execute = AsyncMock(return_value=mock_result)


def mock_execute_scalar_one(mock_db_session: AsyncMock, value):
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = value
    mock_db_session.execute = AsyncMock(return_value=mock_result)


async def test_get_current_portfolio_epoch(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, 3)

    value = await repository.get_current_portfolio_epoch("P1")

    assert value == 3
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(position_state.epoch)" in compiled.lower()
    assert "position_state.portfolio_id = 'P1'" in compiled


async def test_get_active_reprocessing_keys_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 2)

    value = await repository.get_active_reprocessing_keys_count("P1")

    assert value == 2
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in compiled


async def test_get_pending_valuation_jobs_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 4)

    value = await repository.get_pending_valuation_jobs_count("P1")

    assert value == 4
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.status IN ('PENDING', 'PROCESSING')" in compiled


async def test_get_pending_aggregation_jobs_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 1)

    value = await repository.get_pending_aggregation_jobs_count("P1")

    assert value == 1
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_aggregation_jobs" in compiled.lower()
    assert "portfolio_aggregation_jobs.status IN ('PENDING', 'PROCESSING')" in compiled


async def test_get_processing_valuation_jobs_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 2)

    value = await repository.get_processing_valuation_jobs_count("P1")

    assert value == 2
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in compiled


async def test_get_stale_processing_valuation_jobs_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 1)

    value = await repository.get_stale_processing_valuation_jobs_count("P1", stale_minutes=15)

    assert value == 1
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in compiled
    assert "portfolio_valuation_jobs.updated_at <" in compiled


async def test_get_oldest_pending_valuation_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 1))

    value = await repository.get_oldest_pending_valuation_date("P1")

    assert value == date(2025, 8, 1)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "min(portfolio_valuation_jobs.valuation_date)" in compiled.lower()
    assert "portfolio_valuation_jobs.status IN ('PENDING', 'PROCESSING')" in compiled


async def test_get_latest_transaction_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 31))

    value = await repository.get_latest_transaction_date("P1")

    assert value == date(2025, 8, 31)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(date(transactions.transaction_date))" in compiled.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled


async def test_get_latest_transaction_date_as_of(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 15))

    value = await repository.get_latest_transaction_date_as_of("P1", date(2025, 8, 20))

    assert value == date(2025, 8, 15)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "date(transactions.transaction_date) <= '2025-08-20'" in compiled


async def test_get_latest_business_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2026, 3, 1))

    value = await repository.get_latest_business_date()

    assert value == date(2026, 3, 1)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from business_dates" in compiled.lower()


async def test_get_latest_snapshot_date_for_current_epoch(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 30))

    value = await repository.get_latest_snapshot_date_for_current_epoch("P1")

    assert value == date(2025, 8, 30)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from daily_position_snapshots" in compiled.lower()
    assert "join position_state on" in compiled.lower()
    assert "daily_position_snapshots.epoch = position_state.epoch" in compiled


async def test_get_latest_snapshot_date_for_current_epoch_as_of(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 12))

    value = await repository.get_latest_snapshot_date_for_current_epoch_as_of(
        "P1", date(2025, 8, 20)
    )

    assert value == date(2025, 8, 12)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "daily_position_snapshots.date <= '2025-08-20'" in compiled


async def test_get_position_snapshot_history_mismatch_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 0)

    value = await repository.get_position_snapshot_history_mismatch_count("P1")

    assert value == 0
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from (select position_history.portfolio_id" in compiled.lower()
    assert "left outer join" in compiled.lower()
    assert "daily_position_snapshots" in compiled.lower()


async def test_get_position_state(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_state = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_state)

    value = await repository.get_position_state("P1", "S1")

    assert value is mock_state
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.security_id = 'S1'" in compiled


async def test_get_latest_position_history_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 20))

    value = await repository.get_latest_position_history_date("P1", "S1", 2)

    assert value == date(2025, 8, 20)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(position_history.position_date)" in compiled.lower()
    assert "position_history.epoch = 2" in compiled


async def test_get_latest_daily_snapshot_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 22))

    value = await repository.get_latest_daily_snapshot_date("P1", "S1", 2)

    assert value == date(2025, 8, 22)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(daily_position_snapshots.date)" in compiled.lower()
    assert "daily_position_snapshots.epoch = 2" in compiled


async def test_get_latest_valuation_job(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_job = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_job)

    value = await repository.get_latest_valuation_job("P1", "S1", 2)

    assert value is mock_job
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.epoch = 2" in compiled
    assert (
        "ORDER BY portfolio_valuation_jobs.valuation_date DESC, portfolio_valuation_jobs.id DESC"
        in compiled
    )


async def test_get_lineage_keys_count_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 5)

    value = await repository.get_lineage_keys_count(
        portfolio_id="P1", reprocessing_status="CURRENT", security_id="S1"
    )

    assert value == 5
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'CURRENT'" in compiled
    assert "position_state.security_id = 'S1'" in compiled


async def test_get_lineage_keys_query(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["k1", "k2"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_lineage_keys(portfolio_id="P1", skip=5, limit=10)

    assert value == ["k1", "k2"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY position_state.security_id ASC" in compiled
    assert "LIMIT 10 OFFSET 5" in compiled


async def test_get_valuation_jobs_count_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 7)

    value = await repository.get_valuation_jobs_count(portfolio_id="P1", status="PENDING")

    assert value == 7
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.status = 'PENDING'" in compiled


async def test_get_valuation_jobs_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["job1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_valuation_jobs(portfolio_id="P1", skip=0, limit=20, status=None)

    assert value == ["job1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY portfolio_valuation_jobs.valuation_date DESC" in compiled
    assert "LIMIT 20 OFFSET 0" in compiled


async def test_get_aggregation_jobs_count_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 4)

    value = await repository.get_aggregation_jobs_count(portfolio_id="P1", status="PROCESSING")

    assert value == 4
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_aggregation_jobs" in compiled.lower()
    assert "portfolio_aggregation_jobs.status = 'PROCESSING'" in compiled


async def test_get_aggregation_jobs_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["agg1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_aggregation_jobs(portfolio_id="P1", skip=2, limit=5, status=None)

    assert value == ["agg1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY portfolio_aggregation_jobs.aggregation_date DESC" in compiled
    assert "LIMIT 5 OFFSET 2" in compiled


async def test_portfolio_exists_true(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_execute_scalar_one_or_none(mock_db_session, "P1")

    exists = await repository.portfolio_exists("P1")

    assert exists is True


async def test_portfolio_exists_false(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_execute_scalar_one_or_none(mock_db_session, None)

    exists = await repository.portfolio_exists("P404")

    assert exists is False


async def test_get_lineage_keys_query_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["k1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_lineage_keys(
        portfolio_id="P1", skip=0, limit=10, reprocessing_status="CURRENT", security_id="S1"
    )

    assert value == ["k1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "position_state.status = 'CURRENT'" in compiled
    assert "position_state.security_id = 'S1'" in compiled


async def test_get_valuation_jobs_query_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["job1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_valuation_jobs(
        portfolio_id="P1", skip=0, limit=20, status="PENDING"
    )

    assert value == ["job1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs.status = 'PENDING'" in compiled


async def test_get_aggregation_jobs_query_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["agg1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_aggregation_jobs(
        portfolio_id="P1", skip=0, limit=20, status="PROCESSING"
    )

    assert value == ["agg1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_aggregation_jobs.status = 'PROCESSING'" in compiled
