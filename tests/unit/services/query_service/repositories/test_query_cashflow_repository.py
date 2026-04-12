from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.cashflow_repository import CashflowRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = [
        (date(2025, 1, 15), Decimal("10000")),
        (date(2025, 1, 25), Decimal("-2000")),
    ]
    mock_result.scalars.return_value.all.return_value = ["cf1", "cf2"]
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> CashflowRepository:
    return CashflowRepository(mock_db_session)


async def test_get_external_flows_query(repository: CashflowRepository, mock_db_session: AsyncMock):
    result = await repository.get_external_flows("P1", date(2025, 1, 1), date(2025, 1, 31))

    assert result[0][0] == date(2025, 1, 15)
    assert result[0][1] == Decimal("10000")
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "FROM cashflows" in compiled_query
    assert "partition by cashflows.transaction_id" in compiled_query.lower()
    assert "anon_1.portfolio_id = 'P1'" in compiled_query
    assert "anon_1.classification IN ('CASHFLOW_IN', 'CASHFLOW_OUT')" in compiled_query
    assert "anon_1.is_portfolio_flow" in compiled_query


async def test_get_income_cashflows_for_position_query(
    repository: CashflowRepository, mock_db_session: AsyncMock
):
    result = await repository.get_income_cashflows_for_position(
        "P1", "SEC_1", date(2025, 1, 1), date(2025, 3, 31)
    )

    assert result == ["cf1", "cf2"]
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "JOIN position_state ON" in compiled_query
    assert "position_state.epoch = cashflows.epoch" in compiled_query
    assert "cashflows.security_id = 'SEC_1'" in compiled_query
    assert "cashflows.classification = 'INCOME'" in compiled_query


async def test_portfolio_exists_true(repository: CashflowRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "P1"
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("P1")

    assert exists is True


async def test_portfolio_exists_false(repository: CashflowRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("P404")

    assert exists is False


async def test_get_latest_business_date(repository: CashflowRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = date(2026, 3, 1)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    latest = await repository.get_latest_business_date()

    assert latest == date(2026, 3, 1)
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from business_dates" in compiled_query.lower()


async def test_get_portfolio_cashflow_series_query(
    repository: CashflowRepository, mock_db_session: AsyncMock
):
    result = await repository.get_portfolio_cashflow_series(
        "P1", date(2025, 1, 1), date(2025, 1, 31)
    )

    assert result[0][0] == date(2025, 1, 15)
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "sum(anon_1.amount)" in compiled_query.lower()
    assert "partition by cashflows.transaction_id" in compiled_query.lower()
    assert "anon_1.is_portfolio_flow" in compiled_query
    assert "row_number()" in compiled_query.lower()
