"""Immutable operational support records owned by Query Control Plane."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, TypedDict


@dataclass(frozen=True)
class JobHealthSummary:
    pending_jobs: int
    processing_jobs: int
    stale_processing_jobs: int
    failed_jobs: int
    failed_jobs_last_hours: int
    oldest_open_job_date: Optional[date]
    oldest_open_job_id: Optional[int]
    oldest_open_job_correlation_id: Optional[str]
    oldest_open_security_id: Optional[str]


@dataclass(frozen=True)
class ExportJobHealthSummary:
    accepted_jobs: int
    running_jobs: int
    stale_running_jobs: int
    failed_jobs: int
    failed_jobs_last_hours: int
    oldest_open_job_created_at: Optional[datetime]
    oldest_open_job_id: Optional[str]
    oldest_open_request_fingerprint: Optional[str]


@dataclass(frozen=True)
class ReprocessingHealthSummary:
    active_keys: int
    stale_reprocessing_keys: int
    oldest_reprocessing_watermark_date: Optional[date]
    oldest_reprocessing_security_id: Optional[str]
    oldest_reprocessing_epoch: Optional[int]
    oldest_reprocessing_updated_at: Optional[datetime]


@dataclass(frozen=True)
class ReconciliationFindingSummary:
    total_findings: int
    blocking_findings: int
    top_blocking_finding_id: Optional[str]
    top_blocking_finding_type: Optional[str]
    top_blocking_finding_security_id: Optional[str]
    top_blocking_finding_transaction_id: Optional[str]


@dataclass(frozen=True)
class PortfolioControlStageEvidence:
    """Operational evidence for the latest portfolio control stage."""

    stage_id: int
    business_date: date
    epoch: int
    status: str
    last_source_event_type: str | None
    created_at: datetime
    ready_emitted_at: datetime | None
    failure_reason: str | None
    updated_at: datetime

    @property
    def id(self) -> int:
        """Expose the stable API field name without leaking persistence identity."""

        return self.stage_id


@dataclass(frozen=True)
class ReconciliationRunEvidence:
    """Operational evidence for a financial reconciliation run."""

    run_id: str
    reconciliation_type: str
    status: str
    correlation_id: str | None
    requested_by: str | None
    dedupe_key: str | None
    failure_reason: str | None


class LineageKeyEvidence(TypedDict):
    """Typed adapter projection for one portfolio-security processing lineage key."""

    security_id: str
    epoch: int
    watermark_date: date | None
    reprocessing_status: str | None
    latest_position_history_date: date | None
    latest_daily_snapshot_date: date | None
    latest_valuation_job_date: date | None
    latest_valuation_job_id: int | None
    latest_valuation_job_status: str | None
    latest_valuation_job_correlation_id: str | None


@dataclass(frozen=True)
class SnapshotValuationCoverageSummary:
    snapshot_date: Optional[date]
    total_positions: int
    valued_positions: int
    unvalued_positions: int


@dataclass(frozen=True)
class MissingHistoricalFxDependencyRecord:
    transaction_id: str
    security_id: str
    transaction_date: date
    trade_currency: str
    portfolio_currency: str


@dataclass(frozen=True)
class MissingHistoricalFxDependencySummary:
    missing_count: int
    earliest_transaction_date: Optional[date]
    latest_transaction_date: Optional[date]
    sample_records: list[MissingHistoricalFxDependencyRecord]


@dataclass(frozen=True)
class LoadRunProgressSummary:
    portfolios_ingested: int
    transactions_ingested: int
    portfolios_with_snapshots: int
    snapshot_rows: int
    portfolios_with_position_timeseries: int
    position_timeseries_rows: int
    portfolios_with_timeseries: int
    timeseries_rows: int
    pending_valuation_jobs: int
    processing_valuation_jobs: int
    open_valuation_jobs: int
    pending_aggregation_jobs: int
    processing_aggregation_jobs: int
    open_aggregation_jobs: int
    failed_valuation_jobs: int
    failed_aggregation_jobs: int
    oldest_pending_valuation_date: Optional[date]
    oldest_pending_aggregation_date: Optional[date]
    latest_snapshot_date: Optional[date]
    latest_timeseries_date: Optional[date]
    latest_snapshot_materialized_at_utc: Optional[datetime]
    latest_position_timeseries_materialized_at_utc: Optional[datetime]
    latest_portfolio_timeseries_materialized_at_utc: Optional[datetime]
    latest_valuation_job_updated_at_utc: Optional[datetime]
    latest_aggregation_job_updated_at_utc: Optional[datetime]
    completed_valuation_jobs_without_position_timeseries: int
    completed_valuation_portfolios_without_position_timeseries: int
    max_completed_valuation_jobs_without_position_timeseries_single_portfolio: int
    oldest_completed_valuation_without_position_timeseries_at_utc: Optional[datetime]
    valuation_to_position_timeseries_latency_sample_count: int
    valuation_to_position_timeseries_latency_p50_seconds: Optional[float]
    valuation_to_position_timeseries_latency_p95_seconds: Optional[float]
    valuation_to_position_timeseries_latency_max_seconds: Optional[float]
