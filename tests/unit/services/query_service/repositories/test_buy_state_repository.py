from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.repositories.buy_state_repository import BuyStateRepository

pytestmark = pytest.mark.asyncio


def _mock_result(*, scalar_one_or_none=None, scalars_all=None, first=None, all_rows=None):
    result = SimpleNamespace()
    if scalar_one_or_none is not None:
        result.scalar_one_or_none = lambda: scalar_one_or_none
    if scalars_all is not None:
        result.scalars = lambda: SimpleNamespace(all=lambda: scalars_all)
    if first is not None:
        result.first = lambda: first
    if all_rows is not None:
        result.all = lambda: all_rows
    return result


async def test_portfolio_exists_true():
    db = AsyncMock()
    db.execute.return_value = _mock_result(scalar_one_or_none="PORT-1")
    repo = BuyStateRepository(db)
    assert await repo.portfolio_exists("PORT-1") is True


async def test_get_position_lots_returns_rows():
    db = AsyncMock()
    db.execute.return_value = _mock_result(scalars_all=[SimpleNamespace(lot_id="LOT-1")])
    repo = BuyStateRepository(db)
    rows = await repo.get_position_lots("PORT-1", "SEC-1")
    assert len(rows) == 1
    assert rows[0].lot_id == "LOT-1"


async def test_get_accrued_offsets_returns_rows():
    db = AsyncMock()
    db.execute.return_value = _mock_result(scalars_all=[SimpleNamespace(offset_id="AIO-1")])
    repo = BuyStateRepository(db)
    rows = await repo.get_accrued_offsets("PORT-1", "SEC-1")
    assert len(rows) == 1
    assert rows[0].offset_id == "AIO-1"


async def test_get_buy_cash_linkage_returns_tuple():
    db = AsyncMock()
    db.execute.return_value = _mock_result(first=("txn", "cash"))
    repo = BuyStateRepository(db)
    row = await repo.get_buy_cash_linkage("PORT-1", "TXN-1")
    assert row == ("txn", "cash")


async def test_list_portfolio_tax_lots_returns_rows_with_currency():
    db = AsyncMock()
    db.execute.return_value = _mock_result(all_rows=[(SimpleNamespace(lot_id="LOT-1"), "USD")])
    repo = BuyStateRepository(db)

    rows = await repo.list_portfolio_tax_lots(
        portfolio_id="PORT-1",
        as_of_date=date(2026, 4, 10),
        security_ids=["SEC-1"],
        include_closed_lots=False,
        lot_status_filter=None,
        after_sort_key=None,
        limit=251,
    )

    assert rows == [(SimpleNamespace(lot_id="LOT-1"), "USD")]
