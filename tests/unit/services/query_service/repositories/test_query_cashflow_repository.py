from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.cashflow_repository import CashflowRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
    return session


async def test_projected_settlement_cashflow_series_limits_to_external_future_settlements(
    mock_db_session: AsyncMock,
):
    repository = CashflowRepository(mock_db_session)

    await repository.get_projected_settlement_cashflow_series(
        portfolio_id="P1",
        start_date=__import__("datetime").date(2026, 4, 18),
        end_date=__import__("datetime").date(2026, 4, 28),
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.transaction_type IN ('DEPOSIT', 'WITHDRAWAL')" in compiled_query
    assert "date(transactions.settlement_date) BETWEEN '2026-04-18' AND '2026-04-28'" in compiled_query
    assert "date(transactions.transaction_date) < '2026-04-18'" in compiled_query
    assert "transactions.transaction_type = 'BUY'" not in compiled_query
