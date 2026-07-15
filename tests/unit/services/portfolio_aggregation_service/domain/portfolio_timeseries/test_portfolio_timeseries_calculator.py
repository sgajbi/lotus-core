"""Prove pure portfolio-timeseries aggregation arithmetic and scope invariants."""

from datetime import date
from decimal import Decimal

import pytest

from src.services.portfolio_aggregation_service.app.domain.aggregation_records import (
    PortfolioAggregationScope,
    PositionTimeseriesRecord,
)
from src.services.portfolio_aggregation_service.app.domain.portfolio_timeseries import (
    DuplicatePortfolioPositionContribution,
    InvalidPortfolioAggregationScope,
    InvalidPortfolioPositionContribution,
    PortfolioContributionScopeMismatch,
    PortfolioContributionWindowMismatch,
    PortfolioPositionContribution,
    calculate_portfolio_timeseries,
)


def _position(
    security_id: str,
    *,
    portfolio_id: str = "PORT-AGG",
    business_date: date = date(2026, 3, 8),
    epoch: int = 2,
    bod_market_value: Decimal = Decimal("100"),
    bod_cashflow: Decimal = Decimal("1"),
    eod_cashflow: Decimal = Decimal("2"),
    eod_market_value: Decimal = Decimal("110"),
    fees: Decimal = Decimal("0.5"),
) -> PositionTimeseriesRecord:
    return PositionTimeseriesRecord(
        portfolio_id=portfolio_id,
        security_id=security_id,
        date=business_date,
        epoch=epoch,
        bod_market_value=bod_market_value,
        bod_cashflow_portfolio=bod_cashflow,
        eod_cashflow_portfolio=eod_cashflow,
        eod_market_value=eod_market_value,
        fees=fees,
    )


def _scope() -> PortfolioAggregationScope:
    return PortfolioAggregationScope(portfolio_id="PORT-AGG", base_currency="USD")


def test_calculator_sums_position_economics_in_portfolio_currency() -> None:
    result = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=_position("SEC-USD"),
                fx_rate_to_portfolio_currency=Decimal("1"),
            ),
            PortfolioPositionContribution(
                position_timeseries=_position("SEC-EUR"),
                fx_rate_to_portfolio_currency=Decimal("1.2"),
            ),
        ],
    )

    assert result.bod_market_value == Decimal("220.0")
    assert result.bod_cashflow == Decimal("2.2")
    assert result.eod_cashflow == Decimal("4.4")
    assert result.eod_market_value == Decimal("242.0")
    assert result.fees == Decimal("1.10")


def test_calculator_returns_zero_record_for_portfolio_without_positions() -> None:
    result = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[],
    )

    assert result.bod_market_value == Decimal("0")
    assert result.bod_cashflow == Decimal("0")
    assert result.eod_cashflow == Decimal("0")
    assert result.eod_market_value == Decimal("0")
    assert result.fees == Decimal("0")


def test_calculator_rejects_cross_portfolio_contribution() -> None:
    contribution = PortfolioPositionContribution(
        position_timeseries=_position("SEC-OTHER", portfolio_id="OTHER-PORT"),
        fx_rate_to_portfolio_currency=Decimal("1"),
    )

    with pytest.raises(PortfolioContributionScopeMismatch):
        calculate_portfolio_timeseries(
            portfolio=_scope(),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=[contribution],
        )


def test_calculator_rejects_duplicate_security_contribution() -> None:
    contributions = [
        PortfolioPositionContribution(
            position_timeseries=_position("SEC-DUPLICATE"),
            fx_rate_to_portfolio_currency=Decimal("1"),
        ),
        PortfolioPositionContribution(
            position_timeseries=_position(" SEC-DUPLICATE "),
            fx_rate_to_portfolio_currency=Decimal("1"),
        ),
    ]

    with pytest.raises(DuplicatePortfolioPositionContribution):
        calculate_portfolio_timeseries(
            portfolio=_scope(),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=contributions,
        )


def test_calculator_accepts_latest_contribution_within_target_window() -> None:
    result = calculate_portfolio_timeseries(
        portfolio=_scope(),
        aggregation_date=date(2026, 3, 8),
        epoch=2,
        contributions=[
            PortfolioPositionContribution(
                position_timeseries=_position(
                    "SEC-CARRY-FORWARD",
                    business_date=date(2026, 3, 7),
                    epoch=1,
                ),
                fx_rate_to_portfolio_currency=Decimal("1"),
            )
        ],
    )

    assert result.eod_market_value == Decimal("110")


@pytest.mark.parametrize(
    "position",
    [
        _position("SEC-FUTURE-DATE", business_date=date(2026, 3, 9)),
        _position("SEC-FUTURE-EPOCH", epoch=3),
    ],
)
def test_calculator_rejects_future_contribution_outside_target_window(
    position: PositionTimeseriesRecord,
) -> None:
    contribution = PortfolioPositionContribution(
        position_timeseries=position,
        fx_rate_to_portfolio_currency=Decimal("1"),
    )

    with pytest.raises(PortfolioContributionWindowMismatch):
        calculate_portfolio_timeseries(
            portfolio=_scope(),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=[contribution],
        )


def test_calculator_rejects_missing_portfolio_identity() -> None:
    with pytest.raises(InvalidPortfolioAggregationScope):
        calculate_portfolio_timeseries(
            portfolio=PortfolioAggregationScope(portfolio_id=" ", base_currency="USD"),
            aggregation_date=date(2026, 3, 8),
            epoch=2,
            contributions=[],
        )


@pytest.mark.parametrize("fx_rate", [Decimal("0"), Decimal("-1")])
def test_contribution_rejects_non_positive_fx_rate(fx_rate: Decimal) -> None:
    with pytest.raises(InvalidPortfolioPositionContribution):
        PortfolioPositionContribution(
            position_timeseries=_position("SEC-INVALID-FX"),
            fx_rate_to_portfolio_currency=fx_rate,
        )
