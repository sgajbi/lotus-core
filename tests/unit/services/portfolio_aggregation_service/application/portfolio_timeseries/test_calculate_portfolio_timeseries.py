"""Prove source enrichment for portfolio-timeseries calculation."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_aggregation_service.app.application.portfolio_timeseries import (
    CalculatePortfolioTimeseries,
    CurrencyReferenceNotFoundError,
    FxRateNotFoundError,
    InstrumentReferenceNotFoundError,
)


def _position_timeseries(
    security_id: str,
    *,
    business_date: date = date(2026, 3, 8),
    epoch: int = 2,
    bod_market_value: object = Decimal("100"),
    bod_cashflow_portfolio: object = Decimal("1"),
    eod_cashflow_portfolio: object = Decimal("2"),
    eod_market_value: object = Decimal("110"),
    fees: object = Decimal("0.5"),
) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PORT-AGG",
        security_id=security_id,
        date=business_date,
        epoch=epoch,
        bod_market_value=bod_market_value,
        bod_cashflow_portfolio=bod_cashflow_portfolio,
        eod_cashflow_portfolio=eod_cashflow_portfolio,
        eod_market_value=eod_market_value,
        fees=fees,
    )


@pytest.mark.asyncio
async def test_calculation_normalizes_currency_without_fx_lookup() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency=" usd ")
    repository = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[
                SimpleNamespace(security_id="SEC-USD-1", currency="USD"),
                SimpleNamespace(security_id="SEC-USD-2", currency="USD"),
            ]
        ),
        get_fx_rate=AsyncMock(),
    )

    result = await CalculatePortfolioTimeseries().calculate_daily_record(
        portfolio=portfolio,
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        position_timeseries=[
            _position_timeseries("SEC-USD-1"),
            _position_timeseries("SEC-USD-2"),
        ],
        repository=repository,
    )

    assert result.bod_market_value == Decimal("200")
    assert result.eod_market_value == Decimal("220")
    repository.get_instruments_by_ids.assert_awaited_once_with(["SEC-USD-1", "SEC-USD-2"])
    repository.get_fx_rate.assert_not_awaited()


@pytest.mark.asyncio
async def test_calculation_normalizes_sparse_amounts() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repository = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id="SEC-USD", currency="USD")]
        ),
        get_fx_rate=AsyncMock(),
    )

    result = await CalculatePortfolioTimeseries().calculate_daily_record(
        portfolio=portfolio,
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        position_timeseries=[
            _position_timeseries(
                "SEC-USD",
                bod_market_value=" ",
                bod_cashflow_portfolio=" 3.5 ",
                eod_cashflow_portfolio=None,
                eod_market_value=None,
                fees=" 0.25 ",
            )
        ],
        repository=repository,
    )

    assert result.bod_market_value == Decimal("0")
    assert result.bod_cashflow == Decimal("3.5")
    assert result.eod_cashflow == Decimal("0")
    assert result.eod_market_value == Decimal("0")
    assert result.fees == Decimal("0.25")


@pytest.mark.asyncio
async def test_calculation_caches_positive_fx_rates_by_currency_and_date() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repository = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[
                SimpleNamespace(security_id="SEC-EUR-1", currency=" eur "),
                SimpleNamespace(security_id="SEC-EUR-2", currency="EUR"),
            ]
        ),
        get_fx_rate=AsyncMock(return_value=SimpleNamespace(rate="1.2")),
    )

    result = await CalculatePortfolioTimeseries().calculate_daily_record(
        portfolio=portfolio,
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        position_timeseries=[
            _position_timeseries("SEC-EUR-1"),
            _position_timeseries("SEC-EUR-2"),
        ],
        repository=repository,
    )

    assert result.bod_market_value == Decimal("240.0")
    assert result.eod_market_value == Decimal("264.0")
    assert result.fees == Decimal("1.20")
    repository.get_fx_rate.assert_awaited_once_with("EUR", "USD", date(2026, 3, 8))


@pytest.mark.asyncio
async def test_calculation_rejects_non_positive_fx_rate() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repository = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id="SEC-EUR", currency="EUR")]
        ),
        get_fx_rate=AsyncMock(return_value=SimpleNamespace(rate="0")),
    )

    with pytest.raises(FxRateNotFoundError, match="Non-positive FX rate from EUR to USD"):
        await CalculatePortfolioTimeseries().calculate_daily_record(
            portfolio=portfolio,
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            position_timeseries=[_position_timeseries("SEC-EUR")],
            repository=repository,
        )


@pytest.mark.asyncio
async def test_calculation_rejects_missing_instrument_reference() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repository = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id="SEC-USD", currency="USD")]
        ),
        get_fx_rate=AsyncMock(),
    )

    with pytest.raises(
        InstrumentReferenceNotFoundError,
        match="Missing instrument reference data for SEC-MISSING",
    ):
        await CalculatePortfolioTimeseries().calculate_daily_record(
            portfolio=portfolio,
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            position_timeseries=[
                _position_timeseries("SEC-USD"),
                _position_timeseries("SEC-MISSING"),
            ],
            repository=repository,
        )


@pytest.mark.asyncio
async def test_calculation_rejects_missing_portfolio_currency() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency=" ")
    repository = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(),
        get_fx_rate=AsyncMock(),
    )

    with pytest.raises(
        CurrencyReferenceNotFoundError,
        match="requires a portfolio reporting currency",
    ):
        await CalculatePortfolioTimeseries().calculate_daily_record(
            portfolio=portfolio,
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            position_timeseries=[_position_timeseries("SEC-USD")],
            repository=repository,
        )

    repository.get_instruments_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_calculation_rejects_missing_instrument_currency() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repository = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id="SEC-NO-CCY", currency=" ")]
        ),
        get_fx_rate=AsyncMock(),
    )

    with pytest.raises(
        CurrencyReferenceNotFoundError,
        match="Instrument reference data for SEC-NO-CCY has no currency",
    ):
        await CalculatePortfolioTimeseries().calculate_daily_record(
            portfolio=portfolio,
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            position_timeseries=[_position_timeseries("SEC-NO-CCY")],
            repository=repository,
        )

    repository.get_fx_rate.assert_not_awaited()


@pytest.mark.asyncio
async def test_calculation_normalizes_security_identity_before_lookup() -> None:
    portfolio = SimpleNamespace(portfolio_id="PORT-AGG", base_currency="USD")
    repository = SimpleNamespace(
        get_instruments_by_ids=AsyncMock(
            return_value=[SimpleNamespace(security_id=" SEC-USD ", currency="USD")]
        ),
        get_fx_rate=AsyncMock(),
    )

    result = await CalculatePortfolioTimeseries().calculate_daily_record(
        portfolio=portfolio,
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        position_timeseries=[_position_timeseries(" SEC-USD ")],
        repository=repository,
    )

    assert result.eod_market_value == Decimal("110")
    repository.get_instruments_by_ids.assert_awaited_once_with(["SEC-USD"])
