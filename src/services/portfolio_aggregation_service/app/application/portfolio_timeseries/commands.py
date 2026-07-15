"""Framework-neutral commands and outcomes for portfolio-timeseries materialization."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializePortfolioTimeseriesCommand:
    """Identify one claimed portfolio day ready for aggregation."""

    portfolio_id: str
    aggregation_date: date
    correlation_id: str | None = None


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
