"""Immutable models for durable portfolio-aggregation job processing."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class AggregationJobCompletionDisposition(StrEnum):
    """Describe the durable result of releasing one claimed aggregation job."""

    COMPLETE = "COMPLETE"
    REQUEUED = "REQUEUED"
    LOST_OWNERSHIP = "LOST_OWNERSHIP"


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
    aggregation_revision: int
    correlation_id: str | None
    lease: AggregationJobLease

    def __post_init__(self) -> None:
        if self.aggregation_revision < 1:
            raise ValueError("Claimed aggregation revision must be positive.")


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
