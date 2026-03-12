# tests/unit/libs/portfolio-common/test_valuation_job_repository.py
from datetime import date
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from portfolio_common.valuation_job_repository import ValuationJobRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> ValuationJobRepository:
    """Provides an instance of the repository with a mock session."""
    return ValuationJobRepository(mock_db_session)


@patch("portfolio_common.valuation_job_repository.pg_insert")
async def test_upsert_job_builds_correct_statement(
    mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock
):
    """
    GIVEN valuation job details including an epoch
    WHEN upsert_job is called
    THEN it should construct an insert statement with the correct values and
    on_conflict_do_update clause.
    """
    # Arrange
    mock_final_statement = MagicMock()
    mock_pg_insert.return_value.values.return_value.on_conflict_do_update.return_value = (
        mock_final_statement
    )
    latest_epoch_result = MagicMock()
    latest_epoch_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.side_effect = [latest_epoch_result, None]

    job_details = {
        "portfolio_id": "PORT_VJR_01",
        "security_id": "SEC_VJR_01",
        "valuation_date": date(2025, 8, 11),
        "epoch": 1,
        "correlation_id": "corr-vjr-123",
    }

    # Act
    await repository.upsert_job(**job_details)

    # Assert
    mock_pg_insert.return_value.values.assert_called_once()
    called_values = mock_pg_insert.return_value.values.call_args.kwargs
    assert called_values["portfolio_id"] == job_details["portfolio_id"]
    assert called_values["epoch"] == job_details["epoch"]
    assert called_values["status"] == "PENDING"

    mock_pg_insert.return_value.values.return_value.on_conflict_do_update.assert_called_once_with(
        index_elements=["portfolio_id", "security_id", "valuation_date", "epoch"],
        set_=ANY,
        where=ANY,
    )

    assert mock_db_session.execute.await_count == 2
    assert mock_db_session.execute.await_args_list[-1].args[0] == mock_final_statement


@patch("portfolio_common.valuation_job_repository.pg_insert")
async def test_upsert_job_skips_when_newer_epoch_already_exists(
    mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock
):
    latest_epoch_result = MagicMock()
    latest_epoch_result.scalar_one_or_none.return_value = 3
    mock_db_session.execute.return_value = latest_epoch_result

    await repository.upsert_job(
        portfolio_id="PORT_VJR_02",
        security_id="SEC_VJR_02",
        valuation_date=date(2025, 8, 12),
        epoch=2,
        correlation_id="corr-vjr-stale",
    )

    mock_pg_insert.assert_not_called()
    mock_db_session.execute.assert_awaited_once()
