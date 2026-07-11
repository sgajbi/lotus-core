"""Persistence-independent dated FX rate evidence."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FxRateEvidence:
    """One canonical currency-pair rate for a business date."""

    from_currency: str
    to_currency: str
    rate_date: date
    rate: Decimal
    created_at: datetime | None
    updated_at: datetime | None
