# tests/unit/services/query_service/repositories/test_price_repository.py
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.price_repository import MarketPriceRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["price_1", "price_2"]
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> MarketPriceRepository:
    """Provides an instance of the repository with a mock session."""
    return MarketPriceRepository(mock_db_session)


async def test_get_prices_with_filters(
    repository: MarketPriceRepository, mock_db_session: AsyncMock
):
    """
    GIVEN security_id and date filters
    WHEN get_prices is called
    THEN it should construct a SELECT statement with the correct WHERE and ORDER BY clauses.
    """
    # ACT
    await repository.get_prices(
        security_id="S1", start_date=date(2025, 1, 1), end_date=date(2025, 1, 31)
    )

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "WHERE market_prices.security_id = 'S1'" in compiled_query
    assert "AND market_prices.price_date >= '2025-01-01'" in compiled_query
    assert "AND market_prices.price_date <= '2025-01-31'" in compiled_query
    assert "ORDER BY market_prices.price_date ASC" in compiled_query
