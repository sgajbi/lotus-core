"""Domain types for effective-dated FX correction revaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from portfolio_common.domain.currency import normalize_currency_code


@dataclass(frozen=True, slots=True)
class DirectCurrencyPair:
    """A governed direct FX conversion path used by position valuation."""

    from_currency: str
    to_currency: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "from_currency",
            normalize_currency_code(self.from_currency),
        )
        object.__setattr__(
            self,
            "to_currency",
            normalize_currency_code(self.to_currency),
        )
        if self.from_currency == self.to_currency:
            raise ValueError("FX revaluation requires two different currencies")

    @property
    def key(self) -> str:
        """Return the stable direct-pair identity."""
        return f"{self.from_currency}->{self.to_currency}"


@dataclass(frozen=True, slots=True)
class FxRateCorrection:
    """Source-owned correction evidence that can affect portfolio valuations."""

    pair: DirectCurrencyPair
    effective_date: date
    content_hash: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class PositionValuationKey:
    """Current position epoch requiring a valuation job."""

    portfolio_id: str
    security_id: str
    epoch: int


@dataclass(frozen=True, slots=True)
class FxRevaluationPlan:
    """Observable result of staging one FX correction."""

    pair: DirectCurrencyPair
    effective_date: date
    immediate_job_count: int
    durable_replay_staged: bool = True
