"""Shared application contracts for durable position valuation jobs."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Optional


class ValuationJobTransitionOutcome(StrEnum):
    """Classify the result of a processing-owned valuation-job transition."""

    TERMINAL_APPLIED = "TERMINAL_APPLIED"
    REQUEUED = "REQUEUED"
    NOT_OWNED = "NOT_OWNED"


@dataclass(frozen=True, slots=True)
class ValuationJobUpsert:
    """One idempotent position/date/epoch valuation scheduling request."""

    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int
    correlation_id: Optional[str] = None
    source_correction_id: Optional[str] = None
