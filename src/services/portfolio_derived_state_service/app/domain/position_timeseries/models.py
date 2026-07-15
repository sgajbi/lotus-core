"""Immutable inputs and outputs for position-timeseries calculation."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PositionSnapshotRecord:
    """Valued position state required to calculate one position day."""

    portfolio_id: str
    security_id: str
    date: date
    epoch: int
    quantity: Decimal
    cost_basis_local: Decimal | None
    market_value_local: Decimal | None
    source_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PositionCashflowRecord:
    """Cashflow economics required by position-timeseries calculation."""

    transaction_id: str
    cashflow_date: date
    epoch: int
    amount: Decimal
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool


@dataclass(frozen=True, slots=True)
class PositionTimeseriesRecord:
    """Calculated or persisted material state for one position day."""

    portfolio_id: str
    security_id: str
    date: date
    epoch: int
    bod_market_value: Decimal
    bod_cashflow_position: Decimal
    eod_cashflow_position: Decimal
    bod_cashflow_portfolio: Decimal
    eod_cashflow_portfolio: Decimal
    eod_market_value: Decimal
    fees: Decimal
    quantity: Decimal
    cost: Decimal
    materialized_at: datetime | None = None
