from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.reporting_repository import ReportingRepository


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_reporting_repository_lists_portfolios_with_scope_filters() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(
        [SimpleNamespace(portfolio_id="P1"), SimpleNamespace(portfolio_id="P2")]
    )
    repo = ReportingRepository(db)

    rows = await repo.list_portfolios(
        portfolio_ids=["P1", "P2"],
        booking_center_code="SGPB",
    )

    assert len(rows) == 2
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolios.portfolio_id IN ('P1', 'P2')" in compiled
    assert "portfolios.booking_center_code = 'SGPB'" in compiled
    assert "ORDER BY portfolios.portfolio_id ASC" in compiled


@pytest.mark.asyncio
async def test_reporting_repository_latest_snapshot_query_is_latest_non_zero_current_epoch() -> (
    None
):
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(
        [
            (
                SimpleNamespace(portfolio_id="P1"),
                SimpleNamespace(security_id="SEC1"),
                SimpleNamespace(asset_class="EQUITY"),
            )
        ]
    )
    repo = ReportingRepository(db)

    rows = await repo.list_latest_snapshot_rows(
        portfolio_ids=["P1", "P2"],
        as_of_date=date(2026, 3, 27),
    )

    assert len(rows) == 1
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    normalized = compiled.lower()
    assert (
        "row_number() over (partition by daily_position_snapshots.portfolio_id, "
        "daily_position_snapshots.security_id" in normalized
    )
    assert "daily_position_snapshots.date <= '2026-03-27'" in compiled
    assert "daily_position_snapshots.quantity != 0" in compiled
    assert "JOIN position_state" in compiled
    assert "LEFT OUTER JOIN instruments" in compiled
    assert (
        "ORDER BY daily_position_snapshots.portfolio_id ASC, "
        "daily_position_snapshots.security_id ASC" in compiled
    )


@pytest.mark.asyncio
async def test_reporting_repository_get_latest_fx_rate_uses_desc_limit_one() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult([Decimal("1.2500000000")])
    repo = ReportingRepository(db)

    rate = await repo.get_latest_fx_rate(
        from_currency="EUR",
        to_currency="USD",
        as_of_date=date(2026, 3, 27),
    )

    assert rate == Decimal("1.2500000000")
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "fx_rates.from_currency = 'EUR'" in compiled
    assert "fx_rates.to_currency = 'USD'" in compiled
    assert "fx_rates.rate_date <= '2026-03-27'" in compiled
    assert "ORDER BY fx_rates.rate_date DESC" in compiled
    assert "LIMIT 1" in compiled


@pytest.mark.asyncio
async def test_reporting_repository_cash_account_resolution_uses_index_friendly_date_bound() -> (
    None
):
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult(
        [("CASH_USD", "CASH-ACC-USD-001"), ("CASH_SGD", "CASH-ACC-SGD-001")]
    )
    repo = ReportingRepository(db)

    mapping = await repo.get_latest_cash_account_ids(
        portfolio_id="P1",
        cash_security_ids=["CASH_USD", "CASH_SGD"],
        as_of_date=date(2026, 3, 27),
    )

    assert mapping == {
        "CASH_USD": "CASH-ACC-USD-001",
        "CASH_SGD": "CASH-ACC-SGD-001",
    }
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    normalized = compiled.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled
    assert "transactions.settlement_cash_instrument_id IN ('CASH_USD', 'CASH_SGD')" in compiled
    assert "transactions.transaction_date < '2026-03-28 00:00:00'" in compiled
    assert "transactions.settlement_cash_account_id IS NOT NULL" in compiled
    assert (
        "row_number() over (partition by transactions.settlement_cash_instrument_id" in normalized
    )


@pytest.mark.asyncio
async def test_reporting_repository_income_summary_uses_grouped_window_aggregation() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult([])
    repo = ReportingRepository(db)

    await repo.list_income_summary_rows(
        portfolio_ids=["P1", "P2"],
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 27),
        income_types=["DIVIDEND", "INTEREST"],
    )

    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.portfolio_id IN ('P1', 'P2')" in compiled
    assert "transactions.transaction_type IN ('DIVIDEND', 'INTEREST')" in compiled
    assert "transactions.transaction_date >= '2026-01-01 00:00:00'" in compiled
    assert "transactions.transaction_date < '2026-03-28 00:00:00'" in compiled
    assert "GROUP BY portfolios.portfolio_id" in compiled


@pytest.mark.asyncio
async def test_reporting_repository_activity_summary_uses_union_for_withholding_tax_bucket() -> (
    None
):
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult([])
    repo = ReportingRepository(db)

    await repo.list_activity_summary_rows(
        portfolio_ids=["P1"],
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 27),
    )

    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    normalized = compiled.lower()
    assert "union all" in normalized
    assert "'TAXES'" in compiled
    assert "transactions.withholding_tax_amount IS NOT NULL" in compiled
    assert "transactions.transaction_type = 'FEE'" in compiled
    assert "transactions.transaction_type = 'TAX'" in compiled
