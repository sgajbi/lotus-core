"""Framework-neutral commands and outcomes for position-timeseries materialization."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializePositionTimeseriesCommand:
    """Identify one authoritative valuation snapshot to materialize."""

    snapshot_id: int
    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PositionTimeseriesMaterializationResult:
    """Summarize durable effects produced by one materialization command."""

    snapshot_found: bool
    current_day_changed: bool
    dependent_days_changed: int
    dependent_propagation_truncated: bool = False
