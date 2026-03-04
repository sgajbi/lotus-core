# tests/unit/services/query_service/repositories/test_unit_query_position_repo.py
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.position_repository import PositionRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()

    mock_result.all.return_value = [("mock_snapshot", "mock_name")]
    mock_result.scalars.return_value.all.return_value = ["mock_history_1", "mock_history_2"]
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PositionRepository:
    """Provides an instance of the repository with a mock session."""
    return PositionRepository(mock_db_session)


async def test_get_position_history_with_filters(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN various filters
    WHEN get_position_history_by_security is called
    THEN it should construct a SELECT statement with a JOIN to position_state and filter by epoch.
    """
    # ACT
    await repository.get_position_history_by_security(
        portfolio_id="P1", security_id="S1", start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "FROM position_history JOIN position_state" in compiled_query
    assert "position_history.epoch = position_state.epoch" in compiled_query
    assert "WHERE position_history.portfolio_id = 'P1'" in compiled_query
    assert "ORDER BY position_history.position_date ASC" in compiled_query


async def test_get_latest_positions_by_portfolio(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN a portfolio_id
    WHEN get_latest_positions_by_portfolio is called
    THEN it should construct the correct complex query joining with position_state.
    """
    # ACT
    await repository.get_latest_positions_by_portfolio(portfolio_id="P1")

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    # Check for key components of the new complex query
    assert "FROM daily_position_snapshots" in compiled_query
    assert "JOIN position_state ON" in compiled_query
    assert "daily_position_snapshots.epoch = position_state.epoch" in compiled_query
    # Assert that it ranks snapshots by business date and id per security.
    assert "row_number() OVER (PARTITION BY daily_position_snapshots.security_id" in compiled_query
    assert (
        "ORDER BY daily_position_snapshots.date DESC, daily_position_snapshots.id DESC"
        in compiled_query
    )
    # Assert the final query selects only the top-ranked snapshot per security.
    assert "ON daily_position_snapshots.id = anon_1.snapshot_id AND anon_1.rn = 1" in compiled_query


async def test_get_held_since_date_uses_last_zero_cte(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = date(2025, 1, 10)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    held_since = await repository.get_held_since_date("P1", "S1", 3)

    assert held_since == date(2025, 1, 10)
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "WITH last_zero_date AS" in compiled_query
    assert "coalesce(last_zero_date.last_zero_date" in compiled_query.lower()
    assert "position_history.epoch = 3" in compiled_query


async def test_get_position_history_without_date_filters(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    await repository.get_position_history_by_security(portfolio_id="P1", security_id="S1")

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "position_history.position_date >=" not in compiled_query
    assert "position_history.position_date <=" not in compiled_query


async def test_get_latest_position_history_by_portfolio_builds_ranked_query(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    await repository.get_latest_position_history_by_portfolio(portfolio_id="P1")

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "FROM position_history" in compiled_query
    assert "JOIN position_state ON" in compiled_query
    assert "position_history.epoch = position_state.epoch" in compiled_query
    assert "row_number() OVER (PARTITION BY position_history.security_id" in compiled_query
    assert (
        "ORDER BY position_history.position_date DESC, position_history.id DESC" in compiled_query
    )
    assert "ON position_history.id = anon_1.position_history_id AND anon_1.rn = 1" in compiled_query


async def test_get_latest_snapshot_valuation_map_skips_rows_without_security_id(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "security_id": "SEC_A",
            "market_price": 101.0,
            "market_value": 1212.0,
            "unrealized_gain_loss": 112.0,
            "market_value_local": 1212.0,
            "unrealized_gain_loss_local": 112.0,
        },
        {
            "security_id": None,
            "market_price": 1.0,
            "market_value": 1.0,
            "unrealized_gain_loss": 1.0,
            "market_value_local": 1.0,
            "unrealized_gain_loss_local": 1.0,
        },
    ]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    valuation_map = await repository.get_latest_snapshot_valuation_map("P1")

    assert valuation_map == {
        "SEC_A": {
            "market_price": 101.0,
            "market_value": 1212.0,
            "unrealized_gain_loss": 112.0,
            "market_value_local": 1212.0,
            "unrealized_gain_loss_local": 112.0,
        }
    }
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "FROM (" in compiled_query
    assert "daily_position_snapshots.security_id AS security_id" in compiled_query


async def test_portfolio_exists_true(repository: PositionRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "P1"
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("P1")

    assert exists is True


async def test_portfolio_exists_false(repository: PositionRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("P404")

    assert exists is False


async def test_get_latest_business_date(repository: PositionRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = date(2026, 3, 1)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    latest = await repository.get_latest_business_date()

    assert latest == date(2026, 3, 1)
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from business_dates" in compiled_query.lower()


async def test_get_held_since_dates_empty_input(repository: PositionRepository):
    held_since_map = await repository.get_held_since_dates("P1", [])
    assert held_since_map == {}


async def test_get_held_since_dates_non_empty_input_returns_keyed_map(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    row = MagicMock()
    row.security_id = "S1"
    row.epoch = 3
    row.held_since_date = date(2025, 1, 10)
    mock_result.all.return_value = [row]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    held_since_map = await repository.get_held_since_dates("P1", [("S1", 3)])

    assert held_since_map == {("S1", 3): date(2025, 1, 10)}
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "FROM position_history" in compiled_query
    assert "GROUP BY position_history.security_id, position_history.epoch" in compiled_query


async def test_get_latest_positions_by_portfolio_as_of_date_builds_expected_query(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    await repository.get_latest_positions_by_portfolio_as_of_date("P1", date(2025, 1, 31))

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "daily_position_snapshots.date <= '2025-01-31'" in compiled_query
    assert "row_number() OVER (PARTITION BY daily_position_snapshots.security_id" in compiled_query
    assert "daily_position_snapshots.epoch = position_state.epoch" in compiled_query


async def test_get_latest_position_history_by_portfolio_as_of_date_builds_expected_query(
    repository: PositionRepository, mock_db_session: AsyncMock
):
    await repository.get_latest_position_history_by_portfolio_as_of_date("P1", date(2025, 1, 31))

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "position_history.position_date <= '2025-01-31'" in compiled_query
    assert "row_number() OVER (PARTITION BY position_history.security_id" in compiled_query
    assert "position_history.epoch = position_state.epoch" in compiled_query
