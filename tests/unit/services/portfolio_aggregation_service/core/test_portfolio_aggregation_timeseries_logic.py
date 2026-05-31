from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_aggregation_service.app.core.portfolio_timeseries_logic import (
    FxRateNotFoundError,
    PortfolioTimeseriesLogic,
)


def _position_timeseries(
    security_id: str,
    *,
    business_date: date = date(2026, 3, 8),
    bod_market_value: object = Decimal("100"),
    bod_cashflow_portfolio: object = Decimal("1"),
    eod_cashflow_portfolio: object = Decimal("2"),
    eod_market_value: object = Decimal("110"),
    fees: object = Decimal("0.5"),
) -> SimpleNamespace:
    return SimpleNamespace(
        security_id=security_id,
        date=business_date,
        bod_market_value=bod_market_value,
        bod_cashflow_portfolio=bod_cashflow_portfolio,
        eod_cashflow_portfolio=eod_cashflow_portfolio,
        eod_market_value=eod_market_value,
        fees=fees,
    )


@pytest.mark.asyncio
async def test_calculate_daily_record_normalizes_currency_without_fx_lookup() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency=" usd ")
    repo = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id="SEC-USD", currency="USD")]
        ),
        get_fx_rate=AsyncMock(),
    )

    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=portfolio,
        a_date=date(2026, 3, 8),
        epoch=2,
        position_timeseries_list=[_position_timeseries("SEC-USD"), _position_timeseries("SEC-USD")],
        repo=repo,
    )

    assert result.bod_market_value == Decimal("200")
    assert result.bod_cashflow == Decimal("2")
    assert result.eod_cashflow == Decimal("4")
    assert result.eod_market_value == Decimal("220")
    assert result.fees == Decimal("1.0")
    repo.get_instruments_by_ids.assert_awaited_once_with(["SEC-USD"])
    repo.get_fx_rate.assert_not_awaited()


@pytest.mark.asyncio
async def test_calculate_daily_record_normalizes_sparse_amounts() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repo = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id="SEC-USD", currency="USD")]
        ),
        get_fx_rate=AsyncMock(),
    )

    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=portfolio,
        a_date=date(2026, 3, 8),
        epoch=2,
        position_timeseries_list=[
            _position_timeseries(
                "SEC-USD",
                bod_market_value=" ",
                bod_cashflow_portfolio=" 3.5 ",
                eod_cashflow_portfolio=None,
                eod_market_value=None,
                fees=" 0.25 ",
            )
        ],
        repo=repo,
    )

    assert result.bod_market_value == Decimal("0")
    assert result.bod_cashflow == Decimal("3.5")
    assert result.eod_cashflow == Decimal("0")
    assert result.eod_market_value == Decimal("0")
    assert result.fees == Decimal("0.25")


@pytest.mark.asyncio
async def test_calculate_daily_record_caches_positive_fx_rates() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repo = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id="SEC-EUR", currency=" eur ")]
        ),
        get_fx_rate=AsyncMock(return_value=SimpleNamespace(rate="1.2")),
    )

    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=portfolio,
        a_date=date(2026, 3, 8),
        epoch=2,
        position_timeseries_list=[_position_timeseries("SEC-EUR"), _position_timeseries("SEC-EUR")],
        repo=repo,
    )

    assert result.bod_market_value == Decimal("240.0")
    assert result.eod_market_value == Decimal("264.0")
    assert result.fees == Decimal("1.20")
    repo.get_fx_rate.assert_awaited_once_with("EUR", "USD", date(2026, 3, 8))


@pytest.mark.asyncio
async def test_calculate_daily_record_rejects_non_positive_fx_rate() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repo = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id="SEC-EUR", currency="EUR")]
        ),
        get_fx_rate=AsyncMock(return_value=SimpleNamespace(rate="0")),
    )

    with pytest.raises(FxRateNotFoundError, match="Non-positive FX rate from EUR to USD"):
        await PortfolioTimeseriesLogic.calculate_daily_record(
            portfolio=portfolio,
            a_date=date(2026, 3, 8),
            epoch=2,
            position_timeseries_list=[_position_timeseries("SEC-EUR")],
            repo=repo,
        )
