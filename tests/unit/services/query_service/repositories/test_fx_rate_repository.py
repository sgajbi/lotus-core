# tests/unit/services/query_service/repositories/test_fx_rate_repository.py
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.fx_rate_repository import FxRateRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["fx_rate_1", "fx_rate_2"]
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> FxRateRepository:
    """Provides an instance of the repository with a mock session."""
    return FxRateRepository(mock_db_session)


async def test_get_fx_rates_with_filters(repository: FxRateRepository, mock_db_session: AsyncMock):
    """
    GIVEN currency and date filters
    WHEN get_fx_rates is called
    THEN it should construct a SELECT statement with the correct WHERE and ORDER BY clauses.
    """
    # ACT
    await repository.get_fx_rates(
        from_currency="USD",
        to_currency="EUR",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "WHERE fx_rates.from_currency = 'USD'" in compiled_query
    assert "AND fx_rates.to_currency = 'EUR'" in compiled_query
    assert "AND fx_rates.rate_date >= '2025-01-01'" in compiled_query
    assert "AND fx_rates.rate_date <= '2025-01-31'" in compiled_query
    assert "ORDER BY fx_rates.rate_date ASC" in compiled_query
