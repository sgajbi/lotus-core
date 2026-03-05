from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.sell_state_repository import SellStateRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)

    mock_result_list = MagicMock()
    mock_result_list.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]

    mock_result_single = MagicMock()
    mock_result_single.first.return_value = (MagicMock(), MagicMock())

    def execute_side_effect(statement):
        query_text = str(statement.compile(compile_kwargs={"literal_binds": True}))
        if "LEFT OUTER JOIN cashflows" in query_text:
            return mock_result_single
        return mock_result_list

    session.execute = AsyncMock(side_effect=execute_side_effect)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> SellStateRepository:
    return SellStateRepository(mock_db_session)


async def test_get_sell_disposals_filters_portfolio_security_and_sell_type(
    repository: SellStateRepository, mock_db_session: AsyncMock
):
    await repository.get_sell_disposals("PORT-1", "US0378331005")

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.portfolio_id = 'PORT-1'" in compiled
    assert "transactions.security_id = 'US0378331005'" in compiled
    assert "transactions.transaction_type = 'SELL'" in compiled


async def test_get_sell_cash_linkage_joins_cashflow(
    repository: SellStateRepository, mock_db_session: AsyncMock
):
    await repository.get_sell_cash_linkage("PORT-1", "TXN-SELL-1")

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "LEFT OUTER JOIN cashflows" in compiled
    assert "transactions.transaction_id = 'TXN-SELL-1'" in compiled
    assert "transactions.transaction_type = 'SELL'" in compiled


async def test_portfolio_exists_true(repository: SellStateRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "PORT-1"
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("PORT-1")

    assert exists is True


async def test_portfolio_exists_false(repository: SellStateRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("PORT-404")

    assert exists is False
