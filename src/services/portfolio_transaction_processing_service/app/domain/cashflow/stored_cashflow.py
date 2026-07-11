"""Immutable cashflow persistence output used by calculation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StoredCashflow:
    """Expose persisted cashflow values without leaking SQLAlchemy state."""

    cashflow_id: int
    transaction_id: str
    portfolio_id: str
    security_id: str | None
    cashflow_date: date
    epoch: int
    amount: Decimal
    currency: str
    classification: str
    timing: str
    calculation_type: str
    is_position_flow: bool
    is_portfolio_flow: bool
    economic_event_id: str | None = None
    linked_transaction_group_id: str | None = None
