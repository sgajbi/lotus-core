"""Immutable generic simulation state and projection records."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class SimulationSession:
    """Durable lifecycle state for one generic simulation session."""

    session_id: str
    portfolio_id: str
    status: str
    version: int
    created_by: str | None
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class SimulationChange:
    """One persisted change proposed within a simulation session."""

    change_id: str
    session_id: str
    portfolio_id: str
    security_id: str
    transaction_type: str
    quantity: Decimal | None
    price: Decimal | None
    amount: Decimal | None
    currency: str | None
    effective_date: date | None
    metadata: dict[str, Any] | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SimulationPositionBaseline:
    """Current position state used as a generic projection baseline."""

    security_id: str
    position_date: date
    quantity: Decimal
    cost_basis: Decimal | None
    cost_basis_local: Decimal | None
    instrument_name: str
    asset_class: str | None


@dataclass(frozen=True, slots=True)
class SimulationInstrument:
    """Instrument enrichment required by generic simulation projections."""

    security_id: str
    name: str
    asset_class: str | None
