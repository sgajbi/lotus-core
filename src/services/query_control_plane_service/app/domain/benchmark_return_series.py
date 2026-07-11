"""Persistence-independent benchmark return series evidence."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BenchmarkReturnEvidence:
    """One canonical vendor-provided benchmark return observation."""

    series_id: str
    benchmark_id: str
    series_date: date
    benchmark_return: Decimal
    return_period: str
    return_convention: str
    series_currency: str
    quality_status: str
    observed_at: datetime | None
    source_vendor: str | None
    source_record_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
