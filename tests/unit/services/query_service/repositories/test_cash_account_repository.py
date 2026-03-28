from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_service.app.repositories.cash_account_repository import (
    CashAccountRepository,
)


@pytest.mark.asyncio
async def test_portfolio_exists_returns_true_when_portfolio_present() -> None:
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "PORT_001"
    db = AsyncMock()
    db.execute.return_value = execute_result
    repo = CashAccountRepository(db)

    exists = await repo.portfolio_exists("PORT_001")

    assert exists is True
    compiled = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "FROM portfolios" in compiled
    assert "WHERE portfolios.portfolio_id = 'PORT_001'" in compiled


@pytest.mark.asyncio
async def test_portfolio_exists_returns_false_when_portfolio_missing() -> None:
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = execute_result
    repo = CashAccountRepository(db)

    exists = await repo.portfolio_exists("PORT_MISSING")

    assert exists is False


@pytest.mark.asyncio
async def test_list_cash_accounts_applies_as_of_window_and_sort_order() -> None:
    scalars_result = MagicMock()
    scalars_result.all.return_value = ["acc-1", "acc-2"]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    db = AsyncMock()
    db.execute.return_value = execute_result
    repo = CashAccountRepository(db)

    rows = await repo.list_cash_accounts("PORT_001", as_of_date=date(2026, 3, 31))

    assert rows == ["acc-1", "acc-2"]
    compiled = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "FROM cash_account_masters" in compiled
    assert "cash_account_masters.portfolio_id = 'PORT_001'" in compiled
    assert "cash_account_masters.opened_on <=" in compiled
    assert "cash_account_masters.closed_on >=" in compiled
    assert "ORDER BY cash_account_masters.account_currency ASC" in compiled
    assert "cash_account_masters.cash_account_id ASC" in compiled


@pytest.mark.asyncio
async def test_list_cash_accounts_without_as_of_date_uses_portfolio_scope_only() -> None:
    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    db = AsyncMock()
    db.execute.return_value = execute_result
    repo = CashAccountRepository(db)

    rows = await repo.list_cash_accounts("PORT_001")

    assert rows == []
    compiled = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "cash_account_masters.opened_on <=" not in compiled
    assert "cash_account_masters.closed_on >=" not in compiled
