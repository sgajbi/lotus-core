from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.services.analytics_fx_rates import (
    AnalyticsFxRateError,
    get_portfolio_to_reporting_rates,
    get_position_to_portfolio_rate_maps,
    portfolio_to_reporting_rate,
    position_to_portfolio_rate,
)


@pytest.mark.asyncio
async def test_portfolio_to_reporting_rates_skip_same_currency_request() -> None:
    repo = SimpleNamespace(get_fx_rates_map=AsyncMock(return_value={}))

    rates = await get_portfolio_to_reporting_rates(
        repo,
        portfolio_currency=" usd ",
        reporting_currency="USD",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert rates == {}
    repo.get_fx_rates_map.assert_not_called()


@pytest.mark.asyncio
async def test_position_to_portfolio_rate_maps_deduplicate_and_read_sequentially() -> None:
    call_order: list[str] = []

    async def get_fx_rates_map(
        *,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        assert to_currency == "USD"
        assert start_date == date(2025, 1, 1)
        assert end_date == date(2025, 1, 31)
        call_order.append(from_currency)
        return {date(2025, 1, 1): Decimal("1.1") if from_currency == "EUR" else Decimal("1.3")}

    repo = SimpleNamespace(get_fx_rates_map=AsyncMock(side_effect=get_fx_rates_map))

    rates = await get_position_to_portfolio_rate_maps(
        repo,
        position_currencies={" eur ", "EUR", "gbp", "usd", ""},
        portfolio_currency=" usd ",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert rates == {
        "EUR": {date(2025, 1, 1): Decimal("1.1")},
        "GBP": {date(2025, 1, 1): Decimal("1.3")},
        "USD": {},
    }
    assert call_order == ["EUR", "GBP"]


def test_position_to_portfolio_rate_requires_available_cross_rate() -> None:
    with pytest.raises(AnalyticsFxRateError, match="Missing FX rate for EUR/USD"):
        position_to_portfolio_rate(
            position_currency="EUR",
            portfolio_currency="USD",
            valuation_date=date(2025, 1, 1),
            position_to_portfolio_rates={"EUR": {}},
        )


def test_portfolio_to_reporting_rate_returns_identity_for_same_currency() -> None:
    assert portfolio_to_reporting_rate(
        portfolio_currency="USD",
        reporting_currency="USD",
        valuation_date=date(2025, 1, 1),
        fx_rates={},
    ) == Decimal("1")
