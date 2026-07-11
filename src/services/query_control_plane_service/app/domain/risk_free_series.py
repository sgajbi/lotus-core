"""Persistence-independent risk-free rate series evidence."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RiskFreeRateEvidence:
    """One canonical risk-free rate or return observation."""

    series_id: str
    risk_free_curve_id: str
    series_date: date
    value: Decimal
    value_convention: str
    day_count_convention: str | None
    compounding_convention: str | None
    series_currency: str
    quality_status: str
    observed_at: datetime | None
    source_vendor: str | None
    source_record_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
