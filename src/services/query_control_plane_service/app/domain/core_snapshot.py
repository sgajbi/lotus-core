"""Immutable source records used by the Core portfolio snapshot application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CoreSnapshotPortfolio:
    """Portfolio identity and base currency required by snapshot assembly."""

    portfolio_id: str
    base_currency: str


@dataclass(frozen=True, slots=True)
class CoreSnapshotInstrument:
    """Instrument reference fields required by snapshot projection and enrichment."""

    security_id: str
    name: str
    currency: str
    asset_class: str | None
    sector: str | None
    country_of_risk: str | None
    isin: str | None
    issuer_id: str | None
    issuer_name: str | None
    ultimate_parent_issuer_id: str | None
    ultimate_parent_issuer_name: str | None
    liquidity_tier: str | None


@dataclass(frozen=True, slots=True)
class CoreSnapshotPositionSource:
    """Current or historical position evidence flattened at the SQL adapter boundary."""

    security_id: str
    quantity: Decimal
    market_value: Decimal | None
    market_value_local: Decimal | None
    cost_basis: Decimal | None
    cost_basis_local: Decimal | None
    epoch: int
    source_created_at: datetime | None
    source_updated_at: datetime | None
    state_created_at: datetime | None
    state_updated_at: datetime | None
    instrument: CoreSnapshotInstrument


@dataclass(frozen=True, slots=True)
class CoreSnapshotMarketPrice:
    """One observed market price used to value a projected position."""

    price_date: date
    price: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class CoreSnapshotFxRate:
    """One observed FX rate used by snapshot currency conversion."""

    rate_date: date
    rate: Decimal
