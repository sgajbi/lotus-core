# tests/unit/services/persistence_service/repositories/test_portfolio_repository.py
from datetime import date
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import Portfolio as DBPortfolio
from portfolio_common.events import PortfolioEvent

# FIX: Import the actual 'Insert' class for the type check
from sqlalchemy.dialects.postgresql import Insert as PGInsert

from src.services.persistence_service.app.repositories.portfolio_repository import (
    PortfolioRepository,
)

# FIX: Mark tests as async
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PortfolioRepository:
    """Provides an instance of the PortfolioRepository with a mock session."""
    return PortfolioRepository(mock_db_session)


@pytest.fixture
def sample_portfolio_event() -> PortfolioEvent:
    """Provides a sample PortfolioEvent for testing."""
    return PortfolioEvent(
        portfolio_id="PORT_TEST_01",
        base_currency="USD",
        open_date=date(2025, 1, 1),
        client_id="CIF_TEST_1",
        status="ACTIVE",
        risk_exposure="High",
        investment_time_horizon="Long",
        portfolio_type="Discretionary",
        booking_center_code="SG",
    )


# FIX: Convert to a proper async test
async def test_create_or_update_portfolio(
    repository: PortfolioRepository,
    mock_db_session: AsyncMock,
    sample_portfolio_event: PortfolioEvent,
):
    """
    GIVEN a portfolio event
    WHEN create_or_update_portfolio is called
    THEN it should execute a PostgreSQL upsert statement.
    """
    # Act
    result = await repository.create_or_update_portfolio(sample_portfolio_event)

    # Assert
    # 1. Check that execute was called once
    mock_db_session.execute.assert_awaited_once()

    # 2. Check the object returned by the method
    assert isinstance(result, DBPortfolio)
    assert result.portfolio_id == sample_portfolio_event.portfolio_id
    assert result.base_currency == sample_portfolio_event.base_currency

    # 3. Check the SQL statement that was generated and passed to execute
    executed_statement = mock_db_session.execute.call_args[0][0]
    assert isinstance(executed_statement, PGInsert)
