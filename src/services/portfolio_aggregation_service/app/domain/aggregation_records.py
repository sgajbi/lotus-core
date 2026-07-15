"""Immutable inputs and outputs for portfolio aggregation and scheduling."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class AggregationJobCompletionDisposition(StrEnum):
    """Describe the durable result of releasing one claimed aggregation job."""

    COMPLETE = "COMPLETE"
    REQUEUED = "REQUEUED"
    LOST_OWNERSHIP = "LOST_OWNERSHIP"


@dataclass(frozen=True, slots=True)
class PortfolioAggregationScope:
    """Portfolio identity and reporting currency required for aggregation."""

    portfolio_id: str
    base_currency: str


@dataclass(frozen=True, slots=True)
class PositionTimeseriesRecord:
    """Position-day economics consumed by portfolio aggregation."""

    portfolio_id: str
    security_id: str
    date: date
    epoch: int
    bod_market_value: Decimal
    bod_cashflow_portfolio: Decimal
    eod_cashflow_portfolio: Decimal
    eod_market_value: Decimal
    fees: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioTimeseriesRecord:
    """Calculated portfolio-day economics ready for persistence."""

    portfolio_id: str
    date: date
    epoch: int
    bod_market_value: Decimal
    bod_cashflow: Decimal
    eod_cashflow: Decimal
    eod_market_value: Decimal
    fees: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class AggregationJobLease:
    """Fenced ownership of one or more aggregation jobs for a bounded interval."""

    owner: str
    token: str
    expires_at: datetime

    def __post_init__(self) -> None:
        owner = self.owner.strip()
        token = self.token.strip()
        if not owner:
            raise ValueError("Aggregation job lease requires an owner.")
        if len(owner) > 128:
            raise ValueError("Aggregation job lease owner cannot exceed 128 characters.")
        if not token:
            raise ValueError("Aggregation job lease requires a token.")
        if len(token) > 64:
            raise ValueError("Aggregation job lease token cannot exceed 64 characters.")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("Aggregation job lease expiry must be timezone-aware.")
        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "token", token)


@dataclass(frozen=True, slots=True)
class ClaimedAggregationJob:
    """Aggregation work paired with the lease required for terminal writes."""

    id: int
    portfolio_id: str
    aggregation_date: date
    correlation_id: str | None
    lease: AggregationJobLease


@dataclass(frozen=True, slots=True)
class ExpiredAggregationJobRecovery:
    """Count expired claims requeued or failed after retry exhaustion."""

    requeued_count: int
    failed_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AggregationJobBatchResult:
    """Count durable outcomes from one bounded claimed-job batch."""

    complete_count: int = 0
    requeued_count: int = 0
    lost_ownership_count: int = 0
    failed_count: int = 0
    execution_error_count: int = 0

    @property
    def processed_count(self) -> int:
        """Return the total number of attempted jobs."""

        return (
            self.complete_count
            + self.requeued_count
            + self.lost_ownership_count
            + self.failed_count
            + self.execution_error_count
        )


@dataclass(frozen=True, slots=True)
class PortfolioAggregationCompletion:
    """Portfolio-day aggregation identity ready for durable event staging."""

    portfolio_id: str
    aggregation_date: date
    epoch: int
