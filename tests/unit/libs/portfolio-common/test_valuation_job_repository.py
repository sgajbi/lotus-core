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
        index_elements=["portfolio_id", "security_id", "valuation_date", "epoch"], set_=ANY
    )

    mock_db_session.execute.assert_awaited_once_with(mock_final_statement)
