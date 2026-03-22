from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import Cashflow
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.analytics_timeseries_repository import (
    AnalyticsTimeseriesRepository,
)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


@pytest.mark.asyncio
async def test_analytics_timeseries_repository_methods() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = [
        _FakeExecuteResult([SimpleNamespace(portfolio_id="P1")]),
        _FakeExecuteResult([date(2025, 1, 31)]),
        _FakeExecuteResult([SimpleNamespace(valuation_date=date(2025, 1, 1))]),
        _FakeExecuteResult([SimpleNamespace(valuation_date=date(2025, 1, 2))]),
        _FakeExecuteResult([SimpleNamespace(valuation_date=date(2025, 1, 1), security_id="SEC_A")]),
        _FakeExecuteResult(
            [
                SimpleNamespace(rate_date=date(2025, 1, 1), rate=Decimal("1.1200000000")),
                SimpleNamespace(rate_date=date(2025, 1, 2), rate=Decimal("1.1300000000")),
            ]
        ),
        _FakeExecuteResult([3]),
        _FakeExecuteResult([2]),
    ]
    repo = AnalyticsTimeseriesRepository(db)

    portfolio = await repo.get_portfolio("P1")
    assert portfolio is not None

    latest_date = await repo.get_latest_portfolio_timeseries_date("P1")
    assert latest_date == date(2025, 1, 31)

    portfolio_rows = await repo.list_portfolio_timeseries_rows(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        page_size=100,
        cursor_date=None,
    )
    assert len(portfolio_rows) == 1

    portfolio_rows_with_cursor = await repo.list_portfolio_timeseries_rows(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        page_size=100,
        cursor_date=date(2025, 1, 1),
    )
    assert len(portfolio_rows_with_cursor) == 1

    position_rows = await repo.list_position_timeseries_rows(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        page_size=100,
        cursor_date=date(2025, 1, 1),
        cursor_security_id="SEC_A",
        security_ids=["SEC_A"],
        position_ids=["P1:SEC_A"],
        dimension_filters={"asset_class": {"Equity"}, "sector": {"Technology"}, "country": {"US"}},
    )
    assert len(position_rows) == 1

    fx_map = await repo.get_fx_rates_map(
        from_currency="EUR",
        to_currency="USD",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
    assert fx_map[date(2025, 1, 1)] == Decimal("1.1200000000")

    portfolio_snapshot_epoch = await repo.get_portfolio_snapshot_epoch(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
    assert portfolio_snapshot_epoch == 3

    position_snapshot_epoch = await repo.get_position_snapshot_epoch(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        security_ids=["SEC_A"],
        position_ids=["P1:SEC_A"],
        dimension_filters={"asset_class": {"Equity"}, "sector": {"Technology"}, "country": {"US"}},
    )
    assert position_snapshot_epoch == 2


@pytest.mark.asyncio
async def test_timeseries_repository_lists_business_and_observation_dates() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = [
        _FakeExecuteResult(
            [SimpleNamespace(date=date(2025, 1, 1)), SimpleNamespace(date=date(2025, 1, 2))]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(valuation_date=date(2025, 1, 1)),
                SimpleNamespace(valuation_date=date(2025, 1, 2)),
            ]
        ),
    ]
    repo = AnalyticsTimeseriesRepository(db)

    business_dates = await repo.list_business_dates(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
    assert business_dates == [date(2025, 1, 1), date(2025, 1, 2)]
    business_stmt = db.execute.await_args_list[0].args[0]
    business_sql = str(business_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "business_dates.date >= '2025-01-01'" in business_sql
    assert "business_dates.date <= '2025-01-31'" in business_sql

    observation_dates = await repo.list_portfolio_observation_dates(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        snapshot_epoch=6,
    )
    assert observation_dates == [date(2025, 1, 1), date(2025, 1, 2)]
    observation_stmt = db.execute.await_args_list[1].args[0]
    observation_sql = str(observation_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_timeseries.epoch <= 6" in observation_sql
    assert "ORDER BY anon_1.valuation_date ASC" in observation_sql


@pytest.mark.asyncio
async def test_timeseries_repository_applies_snapshot_epoch_filters() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeExecuteResult([])
    repo = AnalyticsTimeseriesRepository(db)

    await repo.list_portfolio_timeseries_rows(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        page_size=10,
        cursor_date=None,
        snapshot_epoch=3,
    )
    portfolio_stmt = db.execute.await_args_list[0].args[0]
    assert "portfolio_timeseries.epoch <= 3" in str(
        portfolio_stmt.compile(compile_kwargs={"literal_binds": True})
    )

    await repo.list_position_timeseries_rows(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        page_size=10,
        cursor_date=None,
        cursor_security_id=None,
        security_ids=[],
        position_ids=[],
        dimension_filters={},
        snapshot_epoch=4,
    )
    position_stmt = db.execute.await_args_list[1].args[0]
    assert "position_timeseries.epoch <= 4" in str(
        position_stmt.compile(compile_kwargs={"literal_binds": True})
    )


@pytest.mark.asyncio
async def test_timeseries_repository_supports_unpaged_position_rows_and_cashflow_queries() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = [
        _FakeExecuteResult([SimpleNamespace(valuation_date=date(2025, 1, 1), security_id="SEC_A")]),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    amount=Decimal("10"),
                    timing="BOD",
                    transaction_id="TXN1",
                )
            ]
        ),
        _FakeExecuteResult(
            [
                SimpleNamespace(
                    valuation_date=date(2025, 1, 1),
                    amount=Decimal("10"),
                    timing="BOD",
                    transaction_id="TXN1",
                )
            ]
        ),
    ]
    repo = AnalyticsTimeseriesRepository(db)

    unpaged_rows = await repo.list_position_timeseries_rows_unpaged(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        snapshot_epoch=2,
    )
    assert len(unpaged_rows) == 1
    unpaged_stmt = db.execute.await_args_list[0].args[0]
    unpaged_sql = str(unpaged_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "position_timeseries.epoch <= 2" in unpaged_sql
    assert "ORDER BY anon_1.valuation_date ASC, anon_1.security_id ASC" in unpaged_sql

    position_cashflow_rows = await repo.list_position_cashflow_rows(
        portfolio_id="P1",
        security_ids=["SEC_A"],
        valuation_dates=[date(2025, 1, 1)],
        snapshot_epoch=3,
    )
    assert len(position_cashflow_rows) == 1
    position_cashflow_stmt = db.execute.await_args_list[1].args[0]
    position_cashflow_sql = str(
        position_cashflow_stmt.compile(compile_kwargs={"literal_binds": True})
    )
    assert "cashflows.is_position_flow IS true" in position_cashflow_sql
    assert "cashflows.security_id" in position_cashflow_sql
    assert "cashflows.epoch <= 3" in position_cashflow_sql

    portfolio_cashflow_rows = await repo.list_portfolio_cashflow_rows(
        portfolio_id="P1",
        valuation_dates=[date(2025, 1, 1)],
        snapshot_epoch=4,
    )
    assert len(portfolio_cashflow_rows) == 1
    portfolio_cashflow_stmt = db.execute.await_args_list[2].args[0]
    portfolio_cashflow_sql = str(
        portfolio_cashflow_stmt.compile(compile_kwargs={"literal_binds": True})
    )
    assert "cashflows.is_portfolio_flow IS true" in portfolio_cashflow_sql
    assert "cashflows.epoch <= 4" in portfolio_cashflow_sql


@pytest.mark.asyncio
async def test_timeseries_repository_short_circuits_empty_cashflow_filters() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = AnalyticsTimeseriesRepository(db)

    assert (
        await repo.list_position_cashflow_rows(
            portfolio_id="P1",
            security_ids=[],
            valuation_dates=[date(2025, 1, 1)],
        )
        == []
    )
    assert (
        await repo.list_position_cashflow_rows(
            portfolio_id="P1",
            security_ids=["SEC_A"],
            valuation_dates=[],
        )
        == []
    )
    assert (
        await repo.list_portfolio_cashflow_rows(
            portfolio_id="P1",
            valuation_dates=[],
        )
        == []
    )
    assert db.execute.await_count == 0


def test_latest_cashflow_rows_stmt_changes_partitioning_for_position_scope() -> None:
    position_stmt = AnalyticsTimeseriesRepository._latest_cashflow_rows_stmt(  # pylint: disable=protected-access
        predicates=[Cashflow.portfolio_id == "P1"],
        include_security_id=True,
    )
    position_sql = str(position_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "PARTITION BY cashflows.transaction_id, cashflows.cashflow_date" in position_sql
    assert "cashflows.security_id" in position_sql
    assert "ORDER BY anon_1.valuation_date ASC, anon_1.security_id ASC" in position_sql

    portfolio_stmt = AnalyticsTimeseriesRepository._latest_cashflow_rows_stmt(  # pylint: disable=protected-access
        predicates=[Cashflow.portfolio_id == "P1"],
        include_security_id=False,
    )
    portfolio_sql = str(portfolio_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "PARTITION BY cashflows.transaction_id, cashflows.cashflow_date" in portfolio_sql
    assert (
        "ORDER BY anon_1.valuation_date ASC, anon_1.timing ASC, "
        "anon_1.transaction_id ASC" in portfolio_sql
    )
