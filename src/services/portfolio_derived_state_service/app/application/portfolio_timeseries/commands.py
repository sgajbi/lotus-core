"""Framework-neutral commands and outcomes for portfolio-timeseries materialization."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializePortfolioTimeseriesCommand:
    """Identify one claimed portfolio day ready for aggregation."""

    job_id: int
    lease_token: str
    portfolio_id: str
    aggregation_date: date
    aggregation_revision: int
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if self.aggregation_revision < 1:
            raise ValueError("Portfolio aggregation revision must be positive.")


class PortfolioTimeseriesMaterializationStatus(StrEnum):
    """Classify the durable outcome of one materialization attempt."""

    COMPLETE = "COMPLETE"
    REQUEUED = "REQUEUED"
    LOST_OWNERSHIP = "LOST_OWNERSHIP"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True, kw_only=True)
class PortfolioTimeseriesMaterializationResult:
    """Summarize durable effects produced by one portfolio-day command."""

    status: PortfolioTimeseriesMaterializationStatus
    target_epoch: int | None = None
    failure_recorded: bool = False
