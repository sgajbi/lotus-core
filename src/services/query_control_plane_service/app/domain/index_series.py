"""Persistence-independent evidence for canonical index series windows."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IndexPriceEvidence:
    """One canonical index price observation."""

    series_id: str
    index_id: str
    series_date: date
    index_price: Decimal
    series_currency: str
    value_convention: str
    quality_status: str
    observed_at: datetime | None
    source_vendor: str | None
    source_record_id: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class IndexReturnEvidence:
    """One canonical vendor-provided index return observation."""

    series_id: str
    index_id: str
    series_date: date
    index_return: Decimal
    return_period: str
    return_convention: str
    series_currency: str
    quality_status: str
    observed_at: datetime | None
    source_vendor: str | None
    source_record_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
