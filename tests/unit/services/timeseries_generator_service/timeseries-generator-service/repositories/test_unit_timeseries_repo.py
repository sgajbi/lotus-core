# tests/unit/services/timeseries_generator_service/repositories/test_unit_timeseries_repo.py
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import (
    PortfolioTimeseries,
    PositionTimeseries,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.timeseries_generator_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a versatile mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()

    mock_result.scalars.return_value.all.return_value = ["item1", "item2"]
    mock_result.scalars.return_value.first.return_value = "item1"
    mock_result.mappings.return_value.all.return_value = [
        {"id": 1, "portfolio_id": "P1", "aggregation_date": date(2025, 1, 1)}
    ]
    mock_result.scalar.return_value = True
    mock_result.fetchall.return_value = [MagicMock(security_id="SEC1")]
    mock_result.rowcount = 1

    session.execute = AsyncMock(return_value=mock_result)

    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> TimeseriesRepository:
    """Provides an instance of the repository with a mock session."""
    return TimeseriesRepository(mock_db_session)


async def test_get_simple_getters(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Tests all simple getter methods that filter by a single ID."""
    await repository.get_portfolio("P1")
    compiled_query = str(
        mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "WHERE portfolios.portfolio_id = 'P1'" in compiled_query

    await repository.get_instrument("S1")
    compiled_query = str(
        mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "WHERE instruments.security_id = 'S1'" in compiled_query


async def test_get_fx_rate(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Verifies the query for the latest FX rate."""
    await repository.get_fx_rate("USD", "EUR", date(2025, 1, 10))
    compiled_query = str(
        mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True})
    )
    assert (
        "WHERE fx_rates.from_currency = 'USD' AND fx_rates.to_currency = 'EUR' AND fx_rates.rate_date <= '2025-01-10'"  # noqa: E501
        in compiled_query
    )
    assert "ORDER BY fx_rates.rate_date DESC" in compiled_query


async def test_upsert_position_timeseries(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    """Verifies the construction of the position timeseries upsert statement."""
    record = PositionTimeseries(
        portfolio_id="P1", security_id="S1", date=date(2025, 1, 10), epoch=1
    )
    await repository.upsert_position_timeseries(record)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_stmt = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "INSERT INTO position_timeseries" in compiled_stmt
    # --- FIX: Assert for the correct primary key including epoch ---
    assert "ON CONFLICT (portfolio_id, security_id, date, epoch) DO UPDATE" in compiled_stmt


async def test_upsert_portfolio_timeseries(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    """Verifies the construction of the portfolio timeseries upsert statement."""
    record = PortfolioTimeseries(portfolio_id="P1", date=date(2025, 1, 10), epoch=1)
    await repository.upsert_portfolio_timeseries(record)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_stmt = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "INSERT INTO portfolio_timeseries" in compiled_stmt
    # --- FIX: Assert for the correct primary key including epoch ---
    assert "ON CONFLICT (portfolio_id, date, epoch) DO UPDATE" in compiled_stmt


async def test_find_and_reset_stale_jobs(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    """Verifies the UPDATE statement for resetting stale jobs."""
    stale_result = MagicMock()
    stale_result.all.return_value = [MagicMock(id=1, attempt_count=1)]
    mock_db_session.execute.side_effect = [stale_result, mock_db_session.execute.return_value]

    await repository.find_and_reset_stale_jobs()

    executed_stmt = mock_db_session.execute.call_args_list[1][0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "UPDATE portfolio_aggregation_jobs" in compiled_query
    assert "SET status='PENDING'" in compiled_query
    assert "updated_at=now()" in compiled_query
    assert "portfolio_aggregation_jobs.id IN" in compiled_query


async def test_find_and_reset_stale_jobs_marks_over_limit_rows_failed(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    stale_result = MagicMock()
    stale_result.all.return_value = [MagicMock(id=1, attempt_count=3)]
    failed_result = MagicMock()
    mock_db_session.execute.side_effect = [stale_result, failed_result]

    reset_count = await repository.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 0
    failed_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_query = str(failed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "SET status='FAILED'" in compiled_query


async def test_get_all_position_timeseries_for_date_uses_latest_position_epoch_within_target_epoch(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.get_all_position_timeseries_for_date("P1", date(2025, 1, 10), 3)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert (
        "row_number() OVER (PARTITION BY position_timeseries.security_id ORDER BY position_timeseries.date DESC, position_timeseries.epoch DESC)"
        in compiled_query
    )
    assert "position_timeseries.date <= '2025-01-10'" in compiled_query
    assert "position_timeseries.epoch <= 3" in compiled_query
    assert "position_timeseries.portfolio_id = anon_1.portfolio_id" in compiled_query
    assert "position_timeseries.security_id = anon_1.security_id" in compiled_query
    assert "position_timeseries.date = anon_1.date" in compiled_query
    assert "position_timeseries.epoch = anon_1.epoch" in compiled_query
    assert "anon_1.rn = 1" in compiled_query


async def test_get_all_cashflows_for_security_date_uses_latest_cashflow_epoch_within_target_epoch(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.get_all_cashflows_for_security_date("P1", "S1", date(2025, 1, 10), 14)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "cashflows.epoch <= 14" in compiled_query
    assert (
        "row_number() OVER (PARTITION BY cashflows.transaction_id ORDER BY cashflows.epoch DESC)"
        in compiled_query
    )
    assert "cashflows.id = anon_1.id" in compiled_query
    assert "anon_1.rn = 1" in compiled_query


async def test_get_last_snapshot_before_uses_latest_snapshot_not_exceeding_target_epoch(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.get_last_snapshot_before("P1", "S1", date(2025, 1, 10), 14)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "daily_position_snapshots.epoch <= 14" in compiled_query
    assert (
        "ORDER BY daily_position_snapshots.date DESC, daily_position_snapshots.epoch DESC"
        in compiled_query
    )


async def test_get_latest_snapshots_for_date_uses_latest_epoch_per_security(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.get_latest_snapshots_for_date("P1", date(2025, 1, 10))

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "daily_position_snapshots.date <= '2025-01-10'" in compiled_query
    assert (
        "GROUP BY daily_position_snapshots.security_id, daily_position_snapshots.date"
        in compiled_query
    )
    assert (
        "row_number() OVER (PARTITION BY anon_2.security_id ORDER BY anon_2.date DESC, anon_2.epoch DESC)"
        in compiled_query
    )
    assert "daily_position_snapshots.date = anon_1.date" in compiled_query
    assert "daily_position_snapshots.epoch = anon_1.epoch" in compiled_query


async def test_find_and_claim_eligible_jobs_does_not_require_prior_portfolio_day(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.find_and_claim_eligible_jobs(batch_size=5)

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert (
        "portfolio_timeseries.date = portfolio_aggregation_jobs.aggregation_date"
        not in compiled_query
    )
    assert "date < portfolio_aggregation_jobs.aggregation_date" not in compiled_query


async def test_find_and_claim_eligible_jobs_increments_attempt_count(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.find_and_claim_eligible_jobs(batch_size=5)

    executed_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "UPDATE portfolio_aggregation_jobs" in compiled_query
    assert "SET status='PROCESSING'" in compiled_query
    assert "attempt_count=(portfolio_aggregation_jobs.attempt_count + 1)" in compiled_query


async def test_find_and_claim_eligible_jobs_has_no_legacy_first_day_gate(
    repository: TimeseriesRepository, mock_db_session: AsyncMock
):
    await repository.find_and_claim_eligible_jobs(batch_size=5)

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "portfolio_aggregation_jobs_1.portfolio_id" not in compiled_query
    assert "NOT (EXISTS" not in compiled_query
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
