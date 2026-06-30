from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.portfolio_repository import PortfolioRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = MagicMock()
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PortfolioRepository:
    return PortfolioRepository(mock_db_session)


async def test_search_portfolio_lookup_ids_filters_searches_and_limits(
    repository: PortfolioRepository,
    mock_db_session: AsyncMock,
):
    mock_result = mock_db_session.execute.return_value
    mock_result.scalars.return_value.all.return_value = ["PF_1"]

    portfolio_ids = await repository.search_portfolio_lookup_ids(
        client_id="CIF-1",
        booking_center_code="SG",
        q="pf",
        limit=5,
    )

    assert portfolio_ids == ["PF_1"]
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "SELECT portfolios.portfolio_id" in compiled_query
    assert "portfolios.client_id = 'CIF-1'" in compiled_query
    assert "portfolios.booking_center_code = 'SG'" in compiled_query
    assert "upper(portfolios.portfolio_id) LIKE '%PF%'" in compiled_query
    assert "ORDER BY portfolios.portfolio_id ASC" in compiled_query
    assert "LIMIT 5" in compiled_query


async def test_list_portfolio_currency_lookup_codes_uses_distinct_limit(
    repository: PortfolioRepository,
    mock_db_session: AsyncMock,
):
    mock_result = mock_db_session.execute.return_value
    mock_result.scalars.return_value.all.return_value = ["USD"]

    codes = await repository.list_currency_lookup_codes(q="us", limit=3)

    assert codes == ["USD"]
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "SELECT DISTINCT upper(trim(portfolios.base_currency))" in compiled_query
    assert "portfolios.base_currency IS NOT NULL" in compiled_query
    assert "trim(portfolios.base_currency) != ''" in compiled_query
    assert "upper(trim(portfolios.base_currency)) LIKE '%US%'" in compiled_query
    assert "ORDER BY upper(trim(portfolios.base_currency)) ASC" in compiled_query
    assert "LIMIT 3" in compiled_query
