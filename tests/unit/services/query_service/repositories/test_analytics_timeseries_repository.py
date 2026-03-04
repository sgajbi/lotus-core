from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
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
