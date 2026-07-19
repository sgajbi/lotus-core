"""Immutable inputs and outputs for portfolio-timeseries calculation."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..position_timeseries.models import PositionTimeseriesRecord
from .errors import InvalidPortfolioPositionContribution


@dataclass(frozen=True, slots=True)
class PortfolioAggregationScope:
    """Portfolio identity and reporting currency required for aggregation."""

    portfolio_id: str
    base_currency: str


@dataclass(frozen=True, slots=True)
class PortfolioTimeseriesRecord:
    """Calculated portfolio-day economics ready for persistence."""

    portfolio_id: str
    date: date
    epoch: int
    bod_market_value: Decimal
    bod_cashflow: Decimal
    eod_cashflow: Decimal
    eod_market_value: Decimal
    fees: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class PortfolioPositionContribution:
    """Pair one position-day record with its portfolio-currency FX rate."""

    position_timeseries: PositionTimeseriesRecord
    fx_rate_to_portfolio_currency: Decimal

    def __post_init__(self) -> None:
        security_id = self.position_timeseries.security_id.strip()
        if not security_id:
            raise InvalidPortfolioPositionContribution(
                "Portfolio position contribution requires a security identity."
            )
        if self.fx_rate_to_portfolio_currency <= 0:
            raise InvalidPortfolioPositionContribution(
                "Portfolio position contribution requires a positive FX rate."
            )


@dataclass(frozen=True, slots=True)
class PortfolioAggregationCompletion:
    """Portfolio-day aggregation identity ready for durable event staging."""

    portfolio_id: str
    aggregation_date: date
    epoch: int
    aggregation_revision: int

    def __post_init__(self) -> None:
        if self.aggregation_revision < 1:
            raise ValueError("Portfolio aggregation completion revision must be positive.")
