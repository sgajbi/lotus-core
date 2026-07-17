"""Shared application contracts for durable position valuation jobs."""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True, slots=True)
class ValuationJobUpsert:
    """One idempotent position/date/epoch valuation scheduling request."""

    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int
    correlation_id: Optional[str] = None
