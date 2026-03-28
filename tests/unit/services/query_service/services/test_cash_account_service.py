from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.cash_account_service import CashAccountService

pytestmark = pytest.mark.asyncio


async def test_get_cash_accounts_returns_master_records() -> None:
    repo = AsyncMock()
    repo.portfolio_exists.return_value = True
    repo.list_cash_accounts.return_value = [
        SimpleNamespace(
            cash_account_id="CASH-ACC-USD-001",
            portfolio_id="P1",
            security_id="CASH_USD",
            display_name="USD Operating Cash",
            account_currency="USD",
            account_role="OPERATING_CASH",
            lifecycle_status="ACTIVE",
            opened_on=date(2026, 1, 1),
            closed_on=None,
            source_system="lotus-manage",
        )
    ]

    with patch(
        "src.services.query_service.app.services.cash_account_service.CashAccountRepository",
        return_value=repo,
    ):
        service = CashAccountService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_accounts("P1", as_of_date=date(2026, 3, 27))

    assert response.portfolio_id == "P1"
    assert response.resolved_as_of_date == date(2026, 3, 27)
    assert response.cash_accounts[0].cash_account_id == "CASH-ACC-USD-001"


async def test_get_cash_accounts_raises_for_missing_portfolio() -> None:
    repo = AsyncMock()
    repo.portfolio_exists.return_value = False

    with patch(
        "src.services.query_service.app.services.cash_account_service.CashAccountRepository",
        return_value=repo,
    ):
        service = CashAccountService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_cash_accounts("P404")
