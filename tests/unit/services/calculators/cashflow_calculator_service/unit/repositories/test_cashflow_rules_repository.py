# tests/unit/services/calculators/cashflow_calculator_service/unit/repositories/test_cashflow_rules_repository.py  # noqa: E501
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cashflow_calculator_service.app.repositories.cashflow_rules_repository import (  # noqa: E501
    CashflowRulesRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["rule1", "rule2"]
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> CashflowRulesRepository:
    """Provides an instance of the repository with a mock session."""
    return CashflowRulesRepository(mock_db_session)


async def test_get_all_rules_constructs_correct_query(
    repository: CashflowRulesRepository, mock_db_session: AsyncMock
):
    """
    GIVEN the repository
    WHEN get_all_rules is called
    THEN it should construct a simple SELECT statement and return the results.
    """
    # ACT
    results = await repository.get_all_rules()

    # ASSERT
    assert len(results) == 2
    mock_db_session.execute.assert_awaited_once()

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "SELECT" in compiled_query
    assert "FROM cashflow_rules" in compiled_query
    assert "ORDER BY cashflow_rules.transaction_type" in compiled_query
