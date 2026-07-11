"""Immutable inputs and outputs for portfolio aggregation and scheduling."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PortfolioAggregationScope:
    """Portfolio identity and reporting currency required for aggregation."""

    portfolio_id: str
    base_currency: str


@dataclass(frozen=True, slots=True)
class PositionTimeseriesRecord:
    """Position-day economics consumed by portfolio aggregation."""

    portfolio_id: str
    security_id: str
    date: date
    epoch: int
    bod_market_value: Decimal
    bod_cashflow_portfolio: Decimal
    eod_cashflow_portfolio: Decimal
    eod_market_value: Decimal
    fees: Decimal


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


@dataclass(frozen=True, slots=True)
class AggregationJobRecord:
    """Claimed aggregation work detached from queue persistence state."""

    id: int
    portfolio_id: str
    aggregation_date: date
    correlation_id: str | None
