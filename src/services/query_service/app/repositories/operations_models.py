from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


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


@dataclass(frozen=True)
class ResetWatermarkReprocessingJobScope:
    security_id_expr: object
    impacted_date_expr: object
    portfolio_scope_exists: object
