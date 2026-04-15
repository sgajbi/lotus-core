# tests/unit/services/timeseries-generator-service/core/test_portfolio_timeseries_logic.py
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import (
    Instrument,
    Portfolio,
    PositionTimeseries,
)

from services.timeseries_generator_service.app.core.portfolio_timeseries_logic import (
    FxRateNotFoundError,
    PortfolioTimeseriesLogic,
)
from src.services.timeseries_generator_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=TimeseriesRepository)
    repo.get_instruments_by_ids = AsyncMock()
    repo.get_fx_rate = AsyncMock()
    repo.get_last_portfolio_timeseries_before = AsyncMock()
    repo.get_latest_snapshots_for_date = AsyncMock()
    return repo


@pytest.fixture
def sample_portfolio() -> Portfolio:
    return Portfolio(portfolio_id="TS_PORT_01", base_currency="USD")


async def test_portfolio_logic_aggregates_correctly_with_epoch(
    mock_repo: AsyncMock, sample_portfolio: Portfolio
):
    """
    Tests that aggregation logic correctly sums market values from snapshots
    of the correct epoch and tags the result with that epoch.
    """
    # ARRANGE
    test_date = date(2025, 8, 8)
    target_epoch = 2

    position_ts_list = [
        PositionTimeseries(
            security_id="SEC_AAPL",
            bod_market_value=Decimal("10000"),
            eod_market_value=Decimal("10000"),
            bod_cashflow_portfolio=Decimal(0),
            eod_cashflow_portfolio=Decimal(0),
            date=test_date,
        ),
        PositionTimeseries(
            security_id="CASH_USD",
            bod_market_value=Decimal("50000"),
            eod_market_value=Decimal("50000"),
            bod_cashflow_portfolio=Decimal(-25),
            eod_cashflow_portfolio=Decimal(0),
            fees=Decimal("25"),
            date=test_date,
        ),
        PositionTimeseries(
            security_id="SEC_IBM",
            bod_market_value=Decimal("7000"),
            eod_market_value=Decimal("7000"),
            bod_cashflow_portfolio=Decimal(0),
            eod_cashflow_portfolio=Decimal(0),
            date=test_date,
        ),
    ]

    mock_repo.get_instruments_by_ids.return_value = [
        Instrument(security_id="SEC_AAPL", currency="USD"),
        Instrument(security_id="CASH_USD", currency="USD"),
        Instrument(security_id="SEC_IBM", currency="USD"),
    ]

    # ACT
    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=sample_portfolio,
        a_date=test_date,
        epoch=target_epoch,
        position_timeseries_list=position_ts_list,
        repo=mock_repo,
    )

    # ASSERT
    assert result.epoch == target_epoch
    assert result.bod_market_value == Decimal("67000")
    assert result.eod_market_value == Decimal("67000")
    assert result.bod_cashflow == Decimal("-25")
    assert result.fees == Decimal("25")


async def test_portfolio_logic_raises_error_if_fx_rate_is_missing(
    mock_repo: AsyncMock, sample_portfolio: Portfolio
):
    """
    GIVEN a position in a foreign currency (EUR) for a USD-based portfolio
    WHEN the required FX rate is not found in the database
    THEN the logic should raise an FxRateNotFoundError.
    """
    # ARRANGE
    test_date = date(2025, 8, 8)

    # Position timeseries for a EUR stock, requiring an FX rate for aggregation
    position_ts_list = [
        PositionTimeseries(
            security_id="EUR_STOCK", bod_cashflow_portfolio=Decimal(100), date=test_date
        )
    ]

    mock_repo.get_instruments_by_ids.return_value = [
        Instrument(security_id="EUR_STOCK", currency="EUR")
    ]
    # Simulate the repository returning no FX rate
    mock_repo.get_fx_rate.return_value = None

    # ACT & ASSERT
    with pytest.raises(FxRateNotFoundError, match="Missing FX rate from EUR to USD"):
        await PortfolioTimeseriesLogic.calculate_daily_record(
            portfolio=sample_portfolio,
            a_date=test_date,
            epoch=1,
            position_timeseries_list=position_ts_list,
            repo=mock_repo,
        )

    # Verify the repository was actually called
    mock_repo.get_fx_rate.assert_awaited_once_with("EUR", "USD", test_date)


# --- NEW TEST ---
async def test_portfolio_logic_handles_non_string_currency(
    mock_repo: AsyncMock, sample_portfolio: Portfolio
):
    """
    GIVEN an Instrument record with a non-string currency value (e.g. from bad data)
    WHEN the logic runs
    THEN it should not raise an AttributeError and should correctly identify the mismatch.
    """
    # ARRANGE
    test_date = date(2025, 8, 8)
    position_ts_list = [PositionTimeseries(security_id="BAD_CURRENCY_STOCK", date=test_date)]

    # Simulate an instrument with a Decimal type for its currency
    mock_instrument = Instrument(security_id="BAD_CURRENCY_STOCK", currency=Decimal("123"))
    mock_repo.get_instruments_by_ids.return_value = [mock_instrument]

    # The expected behavior is an FxRateNotFoundError because '123' != 'USD'
    mock_repo.get_fx_rate.return_value = None

    # ACT & ASSERT
    # The key assertion is that this does NOT raise an AttributeError.
    # It correctly identifies a currency mismatch and tries to get an FX rate.
    # Since the rate is not found, it correctly raises FxRateNotFoundError.
    with pytest.raises(FxRateNotFoundError, match="Missing FX rate from 123 to USD"):
        await PortfolioTimeseriesLogic.calculate_daily_record(
            portfolio=sample_portfolio,
            a_date=test_date,
            epoch=1,
            position_timeseries_list=position_ts_list,
            repo=mock_repo,
        )


async def test_portfolio_logic_uses_position_timeseries_for_bod_and_eod_reconciliation(
    mock_repo: AsyncMock, sample_portfolio: Portfolio
):
    test_date = date(2025, 8, 8)
    position_ts_list = [
        PositionTimeseries(
            security_id="SEC_AAPL",
            date=test_date,
            bod_market_value=Decimal("10000"),
            eod_market_value=Decimal("12000"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
        ),
        PositionTimeseries(
            security_id="CASH_USD",
            date=test_date,
            bod_market_value=Decimal("5000"),
            eod_market_value=Decimal("3000"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
        ),
    ]

    mock_repo.get_instruments_by_ids.return_value = [
        Instrument(security_id="SEC_AAPL", currency="USD"),
        Instrument(security_id="CASH_USD", currency="USD"),
    ]
    mock_repo.get_last_portfolio_timeseries_before.return_value = SimpleNamespace(
        eod_market_value=Decimal("9000")
    )

    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=sample_portfolio,
        a_date=test_date,
        epoch=2,
        position_timeseries_list=position_ts_list,
        repo=mock_repo,
    )

    assert result.bod_market_value == Decimal("15000")
    assert result.eod_market_value == Decimal("15000")
    mock_repo.get_last_portfolio_timeseries_before.assert_not_awaited()
    mock_repo.get_latest_snapshots_for_date.assert_not_awaited()


async def test_portfolio_logic_uses_explicit_fee_field_not_negative_external_flow_signs(
    mock_repo: AsyncMock, sample_portfolio: Portfolio
):
    test_date = date(2026, 3, 26)
    position_ts_list = [
        PositionTimeseries(
            security_id="CASH_USD",
            date=test_date,
            bod_market_value=Decimal("100000"),
            eod_market_value=Decimal("75000"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("-25000"),
            fees=Decimal("0"),
        ),
        PositionTimeseries(
            security_id="FEE_LEDGER",
            date=test_date,
            bod_market_value=Decimal("0"),
            eod_market_value=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("-275"),
            fees=Decimal("275"),
        ),
    ]

    mock_repo.get_instruments_by_ids.return_value = [
        Instrument(security_id="CASH_USD", currency="USD"),
        Instrument(security_id="FEE_LEDGER", currency="USD"),
    ]

    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=sample_portfolio,
        a_date=test_date,
        epoch=14,
        position_timeseries_list=position_ts_list,
        repo=mock_repo,
    )

    assert result.eod_cashflow == Decimal("-25275")
    assert result.fees == Decimal("275")


async def test_portfolio_logic_uses_position_row_date_for_carried_forward_fx_conversion(
    mock_repo: AsyncMock, sample_portfolio: Portfolio
):
    target_date = date(2026, 3, 12)
    carried_forward_date = date(2026, 3, 9)
    position_ts_list = [
        PositionTimeseries(
            security_id="EUR_FUND",
            date=carried_forward_date,
            bod_market_value=Decimal("159900"),
            eod_market_value=Decimal("159901.568"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            fees=Decimal("0"),
        ),
        PositionTimeseries(
            security_id="USD_CASH",
            date=target_date,
            bod_market_value=Decimal("144622"),
            eod_market_value=Decimal("144347"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("-275"),
            fees=Decimal("275"),
        ),
    ]

    mock_repo.get_instruments_by_ids.return_value = [
        Instrument(security_id="EUR_FUND", currency="EUR"),
        Instrument(security_id="USD_CASH", currency="USD"),
    ]

    async def get_fx_rate_side_effect(from_currency: str, to_currency: str, fx_date: date):
        assert from_currency == "EUR"
        assert to_currency == "USD"
        assert fx_date == carried_forward_date
        return SimpleNamespace(rate=Decimal("1.104259"))

    mock_repo.get_fx_rate.side_effect = get_fx_rate_side_effect

    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=sample_portfolio,
        a_date=target_date,
        epoch=14,
        position_timeseries_list=position_ts_list,
        repo=mock_repo,
    )

    assert result.eod_market_value == Decimal("320919.745578112")
    assert result.eod_cashflow == Decimal("-275")
    assert result.fees == Decimal("275")
    mock_repo.get_fx_rate.assert_awaited_once_with("EUR", "USD", carried_forward_date)
