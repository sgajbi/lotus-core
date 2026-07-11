from datetime import UTC, date, datetime
from decimal import Decimal
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


def _position_lot_row() -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PORT-1",
        security_id=" SEC-1 ",
        instrument_id=" INST-1 ",
        lot_id="LOT-1",
        open_quantity=Decimal("100.0000000000"),
        original_quantity=Decimal("150.0000000000"),
        acquisition_date=date(2026, 3, 25),
        lot_cost_base=Decimal("15005.5000000000"),
        lot_cost_local=Decimal("15005.5000000000"),
        source_transaction_id="TXN-1",
        source_system="OMS_PRIMARY",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        updated_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
    )


async def test_portfolio_exists_true():
    db = AsyncMock()
    db.execute.return_value = _mock_result(scalar_one_or_none="PORT-1")
    repo = BuyStateRepository(db)
    assert await repo.portfolio_exists("PORT-1") is True


async def test_get_position_lots_returns_rows():
    db = AsyncMock()
    db.execute.return_value = _mock_result(scalars_all=[SimpleNamespace(lot_id="LOT-1")])
    repo = BuyStateRepository(db)
    rows = await repo.get_position_lots("PORT-1", " SEC-1 ")
    assert len(rows) == 1
    assert rows[0].lot_id == "LOT-1"
    executed_stmt = db.execute.call_args.args[0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(position_lot_state.security_id) = 'SEC-1'" in compiled_query


async def test_get_accrued_offsets_returns_rows():
    db = AsyncMock()
    db.execute.return_value = _mock_result(scalars_all=[SimpleNamespace(offset_id="AIO-1")])
    repo = BuyStateRepository(db)
    rows = await repo.get_accrued_offsets("PORT-1", " SEC-1 ")
    assert len(rows) == 1
    assert rows[0].offset_id == "AIO-1"
    executed_stmt = db.execute.call_args.args[0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(accrued_income_offset_state.security_id) = 'SEC-1'" in compiled_query


async def test_get_position_lots_skips_blank_security_id():
    db = AsyncMock()
    repo = BuyStateRepository(db)

    rows = await repo.get_position_lots("PORT-1", " ")

    assert rows == []
    db.execute.assert_not_awaited()


async def test_get_accrued_offsets_skips_blank_security_id():
    db = AsyncMock()
    repo = BuyStateRepository(db)

    rows = await repo.get_accrued_offsets("PORT-1", " ")

    assert rows == []
    db.execute.assert_not_awaited()


async def test_get_buy_cash_linkage_returns_tuple():
    db = AsyncMock()
    db.execute.return_value = _mock_result(first=("txn", "cash"))
    repo = BuyStateRepository(db)
    row = await repo.get_buy_cash_linkage("PORT-1", "TXN-1")
    assert row == ("txn", "cash")
