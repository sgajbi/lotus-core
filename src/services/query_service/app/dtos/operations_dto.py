from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .source_data_product_identity import product_name_field, product_version_field
from ..support_policy import (
    CALCULATOR_SLO_FAILED_WINDOW_DESCRIPTION,
    SUPPORT_FAILED_WINDOW_DESCRIPTION,
    SUPPORT_STALE_THRESHOLD_DESCRIPTION,
)


class SupportOverviewResponse(BaseModel):
    portfolio_id: str = Field(..., description="Unique portfolio identifier.", examples=["PF-001"])
    business_date: Optional[date] = Field(
        None,
        description=(
            "Latest business date from the default business calendar used as the "
            "booked-state boundary."
        ),
        examples=["2025-12-30"],
    )
    current_epoch: Optional[int] = Field(
        None,
        description="Current active epoch for the portfolio across position state keys.",
        examples=[3],
    )
    stale_threshold_minutes: int = Field(
        ...,
        description=SUPPORT_STALE_THRESHOLD_DESCRIPTION,
        examples=[15],
    )
    failed_window_hours: int = Field(
        ...,
        description=SUPPORT_FAILED_WINDOW_DESCRIPTION,
        examples=[24],
    )
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this support overview snapshot was generated.",
        examples=["2026-03-14T10:45:00Z"],
    )
    active_reprocessing_keys: int = Field(
        ...,
        description="Number of portfolio-security keys currently marked REPROCESSING.",
        examples=[2],
    )
    stale_reprocessing_keys: int = Field(
        ...,
        description=(
            "Number of REPROCESSING portfolio-security keys whose last update is older than "
            "the support stale threshold."
        ),
        examples=[1],
    )
    oldest_reprocessing_watermark_date: Optional[date] = Field(
        None,
        description=(
            "Oldest replay watermark date among portfolio-security keys currently marked "
            "REPROCESSING."
        ),
        examples=["2025-11-03"],
    )
    oldest_reprocessing_security_id: Optional[str] = Field(
        None,
        description=(
            "Security identifier for the oldest portfolio-security key currently marked "
            "REPROCESSING."
        ),
        examples=["AAPL"],
    )
    oldest_reprocessing_epoch: Optional[int] = Field(
        None,
        description=(
            "Current epoch of the oldest portfolio-security key currently marked REPROCESSING."
        ),
        examples=[3],
    )
    oldest_reprocessing_updated_at: Optional[datetime] = Field(
        None,
        description=(
            "UTC timestamp of the most recent durable update for the oldest "
            "portfolio-security key currently marked REPROCESSING."
        ),
        examples=["2026-03-13T10:15:09Z"],
    )
    reprocessing_backlog_age_days: Optional[int] = Field(
        None,
        description=(
            "Backlog age in days computed from oldest_reprocessing_watermark_date to "
            "business_date (or current UTC date when business_date is missing)."
        ),
        examples=[119],
    )
    pending_valuation_jobs: int = Field(
        ...,
        description="Number of pending/processing valuation jobs for the portfolio.",
        examples=[14],
    )
    processing_valuation_jobs: int = Field(
        ...,
        description="Number of valuation jobs currently in PROCESSING state.",
        examples=[3],
    )
    stale_processing_valuation_jobs: int = Field(
        ...,
        description="Number of PROCESSING valuation jobs older than the support stale threshold.",
        examples=[1],
    )
    failed_valuation_jobs: int = Field(
        ...,
        description="Number of valuation jobs currently in FAILED terminal state.",
        examples=[2],
    )
    failed_valuation_jobs_within_window: int = Field(
        ...,
        description=(
            "Number of valuation jobs that moved to FAILED state within the configured "
            "failed-job window."
        ),
        examples=[1],
    )
    oldest_pending_valuation_date: Optional[date] = Field(
        None,
        description="Oldest valuation date among pending/processing jobs for backlog analysis.",
        examples=["2025-11-03"],
    )
    oldest_pending_valuation_job_id: Optional[int] = Field(
        None,
        description="Durable job id for the oldest open valuation job in the backlog.",
        examples=[8801],
    )
    oldest_pending_valuation_security_id: Optional[str] = Field(
        None,
        description="Security identifier for the oldest open valuation job in the backlog.",
        examples=["SEC-US-IBM"],
    )
    oldest_pending_valuation_correlation_id: Optional[str] = Field(
        None,
        description=(
            "Durable correlation identifier for the oldest open valuation job in the backlog."
        ),
        examples=["corr-val-20260313-001"],
    )
    valuation_backlog_age_days: Optional[int] = Field(
        None,
        description=(
            "Backlog age in days computed from oldest pending valuation date "
            "to business_date (or current UTC date when business_date is missing)."
        ),
        examples=[119],
    )
    pending_aggregation_jobs: int = Field(
        ...,
        description="Number of pending/processing portfolio aggregation jobs for the portfolio.",
        examples=[1],
    )
    processing_aggregation_jobs: int = Field(
        ...,
        description="Number of aggregation jobs currently in PROCESSING state.",
        examples=[0],
    )
    stale_processing_aggregation_jobs: int = Field(
        ...,
        description=(
            "Number of PROCESSING aggregation jobs older than the support stale threshold."
        ),
        examples=[0],
    )
    failed_aggregation_jobs: int = Field(
        ...,
        description="Number of aggregation jobs currently in FAILED terminal state.",
        examples=[1],
    )
    failed_aggregation_jobs_within_window: int = Field(
        ...,
        description=(
            "Number of aggregation jobs that moved to FAILED state within the configured "
            "failed-job window."
        ),
        examples=[0],
    )
    oldest_pending_aggregation_date: Optional[date] = Field(
        None,
        description="Oldest aggregation date among pending/processing jobs for backlog analysis.",
        examples=["2025-12-29"],
    )
    oldest_pending_aggregation_job_id: Optional[int] = Field(
        None,
        description="Durable job id for the oldest open aggregation job in the backlog.",
        examples=[4402],
    )
    oldest_pending_aggregation_correlation_id: Optional[str] = Field(
        None,
        description=(
            "Durable correlation identifier for the oldest open aggregation job in the backlog."
        ),
        examples=["corr-agg-20260313-001"],
    )
    aggregation_backlog_age_days: Optional[int] = Field(
        None,
        description=(
            "Backlog age in days computed from oldest pending aggregation date "
            "to business_date (or current UTC date when business_date is missing)."
        ),
        examples=[1],
    )
    pending_analytics_export_jobs: int = Field(
        ...,
        description="Number of analytics export jobs currently waiting in ACCEPTED state.",
        examples=[2],
    )
    processing_analytics_export_jobs: int = Field(
        ...,
        description="Number of analytics export jobs currently in RUNNING state.",
        examples=[1],
    )
    stale_processing_analytics_export_jobs: int = Field(
        ...,
        description=(
            "Number of analytics export jobs in RUNNING state whose last update is older than "
            "the support stale threshold."
        ),
        examples=[0],
    )
    failed_analytics_export_jobs: int = Field(
        ...,
        description="Number of analytics export jobs currently in FAILED terminal state.",
        examples=[1],
    )
    failed_analytics_export_jobs_within_window: int = Field(
        ...,
        description=(
            "Number of analytics export jobs that moved to FAILED state within the configured "
            "failed-job window."
        ),
        examples=[1],
    )
    oldest_pending_analytics_export_created_at: Optional[datetime] = Field(
        None,
        description=(
            "Oldest created_at timestamp among analytics export jobs still waiting or running."
        ),
        examples=["2026-03-13T10:15:00Z"],
    )
    oldest_pending_analytics_export_job_id: Optional[str] = Field(
        None,
        description="Durable job id for the oldest open analytics export job in the backlog.",
        examples=["aexp_20260313_00012"],
    )
    oldest_pending_analytics_export_request_fingerprint: Optional[str] = Field(
        None,
        description="Request fingerprint for the oldest open analytics export job in the backlog.",
        examples=["pf-001:positions:csv:2026-03-13"],
    )
    analytics_export_backlog_age_minutes: Optional[int] = Field(
        None,
        description=(
            "Backlog age in minutes from the oldest waiting/running analytics export job to the "
            "current UTC time."
        ),
        examples=[42],
    )
    latest_transaction_date: Optional[date] = Field(
        None,
        description="Most recent transaction business date observed for the portfolio (unbounded).",
        examples=["2026-01-05"],
    )
    latest_booked_transaction_date: Optional[date] = Field(
        None,
        description=(
            "Most recent transaction business date observed for the portfolio up to business_date."
        ),
        examples=["2025-12-30"],
    )
    latest_position_snapshot_date: Optional[date] = Field(
        None,
        description=(
            "Most recent daily position snapshot date in the current epoch "
            "(unbounded, may include projected state)."
        ),
        examples=["2026-01-05"],
    )
    latest_booked_position_snapshot_date: Optional[date] = Field(
        None,
        description=(
            "Most recent daily position snapshot date in the current epoch up to business_date."
        ),
        examples=["2025-12-30"],
    )
    position_snapshot_history_mismatch_count: int = Field(
        ...,
        description=(
            "Count of position keys where position_history exists but no matching "
            "daily_position_snapshot exists for the same portfolio/security/epoch."
        ),
        examples=[0],
    )
    controls_business_date: Optional[date] = Field(
        None,
        description=(
            "Business date for the latest portfolio-day financial reconciliation control stage "
            "tracked by the orchestrator."
        ),
        examples=["2025-12-30"],
    )
    controls_stage_id: Optional[int] = Field(
        None,
        description=(
            "Durable database identifier of the latest portfolio-day financial reconciliation "
            "control stage."
        ),
        examples=[701],
    )
    controls_last_source_event_type: Optional[str] = Field(
        None,
        description=(
            "Most recent durable source event type recorded on the latest portfolio-day "
            "financial reconciliation control stage."
        ),
        examples=["portfolio_day.reconciliation.completed"],
    )
    controls_created_at: Optional[datetime] = Field(
        None,
        description=(
            "UTC timestamp when the latest portfolio-day financial reconciliation control "
            "stage row was first created."
        ),
        examples=["2026-03-13T10:10:00Z"],
    )
    controls_ready_emitted_at: Optional[datetime] = Field(
        None,
        description=(
            "UTC timestamp when the latest portfolio-day financial reconciliation control "
            "stage emitted readiness, if readiness has been emitted."
        ),
        examples=["2026-03-13T10:15:05Z"],
    )
    controls_epoch: Optional[int] = Field(
        None,
        description=(
            "Epoch associated with the latest portfolio-day financial reconciliation stage."
        ),
        examples=[3],
    )
    controls_status: Optional[str] = Field(
        None,
        description=(
            "Latest orchestrator-owned financial reconciliation control status "
            "(for example COMPLETED, REQUIRES_REPLAY, FAILED)."
        ),
        examples=["COMPLETED"],
    )
    controls_failure_reason: Optional[str] = Field(
        None,
        description=(
            "Durable failure reason recorded on the latest portfolio-day financial "
            "reconciliation control stage, when the latest stage is failed."
        ),
        examples=["Tolerance exceeded for portfolio totals."],
    )
    controls_latest_reconciliation_run_id: Optional[str] = Field(
        None,
        description=(
            "Durable reconciliation run identifier for the latest reconciliation run on the "
            "same portfolio-day and epoch as the latest control stage."
        ),
        examples=["recon_1234567890abcdef"],
    )
    controls_latest_reconciliation_type: Optional[str] = Field(
        None,
        description=(
            "Reconciliation type for the latest reconciliation run on the same portfolio-day "
            "and epoch as the latest control stage."
        ),
        examples=["transaction_cashflow"],
    )
    controls_latest_reconciliation_status: Optional[str] = Field(
        None,
        description=(
            "Durable lifecycle status for the latest reconciliation run on the same "
            "portfolio-day and epoch as the latest control stage."
        ),
        examples=["FAILED"],
    )
    controls_latest_reconciliation_correlation_id: Optional[str] = Field(
        None,
        description=(
            "Durable correlation identifier for the latest reconciliation run on the same "
            "portfolio-day and epoch as the latest control stage."
        ),
        examples=["corr-recon-20260313-001"],
    )
    controls_latest_reconciliation_requested_by: Optional[str] = Field(
        None,
        description=(
            "Principal or subsystem that requested the latest reconciliation run on the "
            "same portfolio-day and epoch as the latest control stage."
        ),
        examples=["pipeline_orchestrator_service"],
    )
    controls_latest_reconciliation_dedupe_key: Optional[str] = Field(
        None,
        description=(
            "Stable deduplication key for the latest reconciliation run on the same "
            "portfolio-day and epoch as the latest control stage."
        ),
        examples=["recon:transaction_cashflow:PF-001:2025-08-31:3"],
    )
    controls_latest_reconciliation_failure_reason: Optional[str] = Field(
        None,
        description=(
            "Failure reason recorded on the latest reconciliation run on the same "
            "portfolio-day and epoch as the latest control stage."
        ),
        examples=["Tolerance exceeded for portfolio totals."],
    )
    controls_latest_reconciliation_total_findings: Optional[int] = Field(
        None,
        description=(
            "Total durable finding count recorded on the latest reconciliation run on the "
            "same portfolio-day and epoch as the latest control stage."
        ),
        examples=[3],
    )
    controls_latest_reconciliation_blocking_findings: Optional[int] = Field(
        None,
        description=(
            "Number of blocking reconciliation findings recorded on the latest "
            "reconciliation run on the same portfolio-day and epoch as the latest "
            "control stage."
        ),
        examples=[1],
    )
    controls_latest_blocking_finding_id: Optional[str] = Field(
        None,
        description=(
            "Durable identifier of the most recent blocking reconciliation finding on the "
            "latest reconciliation run linked to the latest control stage."
        ),
        examples=["rf_1234567890abcdef"],
    )
    controls_latest_blocking_finding_type: Optional[str] = Field(
        None,
        description=(
            "Finding type for the most recent blocking reconciliation finding on the "
            "latest reconciliation run linked to the latest control stage."
        ),
        examples=["missing_cashflow"],
    )
    controls_latest_blocking_finding_security_id: Optional[str] = Field(
        None,
        description=(
            "Security identifier attached to the most recent blocking reconciliation "
            "finding on the latest reconciliation run linked to the latest control stage."
        ),
        examples=["SEC-US-IBM"],
    )
    controls_latest_blocking_finding_transaction_id: Optional[str] = Field(
        None,
        description=(
            "Transaction identifier attached to the most recent blocking reconciliation "
            "finding on the latest reconciliation run linked to the latest control stage."
        ),
        examples=["txn_20260313_0001"],
    )
    controls_last_updated_at: Optional[datetime] = Field(
        None,
        description=(
            "UTC timestamp of the most recent durable lifecycle update for the latest "
            "portfolio-day financial reconciliation control stage."
        ),
        examples=["2026-03-13T10:15:09Z"],
    )
    controls_blocking: bool = Field(
        ...,
        description=(
            "True when the latest portfolio-day controls require replay or have failed, "
            "and therefore block downstream publication/release decisions."
        ),
        examples=[False],
    )
    publish_allowed: bool = Field(
        ...,
        description=(
            "True only when the latest portfolio-day financial reconciliation controls "
            "permit downstream publication/release."
        ),
        examples=[True],
    )


ReadinessStatus = Literal["READY", "PENDING", "BLOCKED", "NO_ACTIVITY"]
ReadinessSeverity = Literal["INFO", "WARNING", "ERROR"]
ReadinessDomain = Literal["holdings", "pricing", "transactions", "reporting"]


class PortfolioReadinessReason(BaseModel):
    code: str = Field(
        ...,
        description="Stable source-owned reason code explaining the readiness state.",
        examples=["MISSING_HISTORICAL_FX_PREREQUISITE"],
    )
    domain: ReadinessDomain = Field(
        ...,
        description="Readiness domain affected by this reason.",
        examples=["pricing"],
    )
    severity: ReadinessSeverity = Field(
        ...,
        description="Operational severity of the readiness reason.",
        examples=["ERROR"],
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of the readiness condition.",
        examples=[
            "Cross-currency transactions are missing historical FX prerequisites "
            "required for full pricing coverage."
        ],
    )
    affected_transaction_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Affected transaction identifiers when the readiness reason is transaction-scoped."
        ),
        examples=[["TXN-20260328-0001", "TXN-20260328-0002"]],
    )
    affected_security_ids: list[str] = Field(
        default_factory=list,
        description="Affected security identifiers when the readiness reason is security-scoped.",
        examples=[["SEC-EUR-STOCK-001"]],
    )


class PortfolioReadinessBucket(BaseModel):
    status: ReadinessStatus = Field(
        ...,
        description="Source-owned readiness state for this portfolio domain.",
        examples=["READY"],
    )
    reasons: list[PortfolioReadinessReason] = Field(
        default_factory=list,
        description="Source-owned reasons explaining why this readiness bucket is not fully ready.",
    )


class MissingHistoricalFxDependencyRecord(BaseModel):
    transaction_id: str = Field(
        ...,
        description="Cross-currency transaction blocked by missing historical FX.",
        examples=["TXN-20260328-0001"],
    )
    security_id: str = Field(
        ...,
        description="Security identifier carried by the affected transaction.",
        examples=["SEC-EUR-STOCK-001"],
    )
    transaction_date: date = Field(
        ...,
        description="Transaction business date requiring historical FX coverage.",
        examples=["2026-03-18"],
    )
    trade_currency: str = Field(
        ...,
        description="Trade currency on the affected transaction.",
        examples=["EUR"],
    )
    portfolio_currency: str = Field(
        ...,
        description="Portfolio base currency that historical FX conversion is required against.",
        examples=["USD"],
    )


class MissingHistoricalFxDependencySummary(BaseModel):
    missing_count: int = Field(
        ...,
        description="Number of cross-currency transactions missing historical FX prerequisites.",
        examples=[2],
    )
    earliest_transaction_date: Optional[date] = Field(
        None,
        description="Earliest affected transaction date among missing historical FX dependencies.",
        examples=["2026-03-18"],
    )
    latest_transaction_date: Optional[date] = Field(
        None,
        description="Latest affected transaction date among missing historical FX dependencies.",
        examples=["2026-03-20"],
    )
    sample_records: list[MissingHistoricalFxDependencyRecord] = Field(
        default_factory=list,
        description="Representative affected transactions for operator and downstream visibility.",
    )


class PortfolioReadinessResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    requested_as_of_date: Optional[date] = Field(
        None,
        description="Caller-requested as-of date, when one was supplied.",
        examples=["2026-03-28"],
    )
    resolved_as_of_date: Optional[date] = Field(
        None,
        description="Resolved source-owned as-of date used for readiness evaluation.",
        examples=["2026-03-28"],
    )
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this readiness snapshot was generated.",
        examples=["2026-03-28T08:45:00Z"],
    )
    holdings: PortfolioReadinessBucket = Field(
        ...,
        description="Holdings/snapshot coverage readiness for the portfolio.",
    )
    pricing: PortfolioReadinessBucket = Field(
        ...,
        description="Pricing and valuation coverage readiness for the portfolio.",
    )
    transactions: PortfolioReadinessBucket = Field(
        ...,
        description="Ledger and transaction-prerequisite readiness for the portfolio.",
    )
    reporting: PortfolioReadinessBucket = Field(
        ...,
        description="Reporting/publish readiness for the portfolio.",
    )
    blocking_reasons: list[PortfolioReadinessReason] = Field(
        default_factory=list,
        description="Flattened blocking reasons that make the portfolio not fully ready.",
    )
    latest_booked_transaction_date: Optional[date] = Field(
        None,
        description="Most recent portfolio transaction date on or before resolved_as_of_date.",
        examples=["2026-03-28"],
    )
    latest_booked_position_snapshot_date: Optional[date] = Field(
        None,
        description=(
            "Most recent current-epoch position snapshot date on or before resolved_as_of_date."
        ),
        examples=["2026-03-28"],
    )
    current_epoch: Optional[int] = Field(
        None,
        description="Current active epoch for the portfolio across position-state keys.",
        examples=[3],
    )
    position_snapshot_history_mismatch_count: int = Field(
        ...,
        description=(
            "Count of keys where position history exists but no matching current-epoch "
            "snapshot exists."
        ),
        examples=[0],
    )
    snapshot_valuation_total_positions: int = Field(
        ...,
        description="Total current-epoch positions on the latest booked snapshot date.",
        examples=[7],
    )
    snapshot_valuation_valued_positions: int = Field(
        ...,
        description=(
            "Current-epoch positions on the latest booked snapshot date with non-UNVALUED coverage."
        ),
        examples=[7],
    )
    snapshot_valuation_unvalued_positions: int = Field(
        ...,
        description=(
            "Current-epoch positions on the latest booked snapshot date still lacking "
            "valuation coverage."
        ),
        examples=[0],
    )
    controls_status: Optional[str] = Field(
        None,
        description=(
            "Latest financial reconciliation control status relevant to reporting readiness."
        ),
        examples=["COMPLETED"],
    )
    publish_allowed: bool = Field(
        ...,
        description=(
            "Whether the latest source-owned financial controls currently allow "
            "downstream publication."
        ),
        examples=[True],
    )
    missing_historical_fx_dependencies: MissingHistoricalFxDependencySummary = Field(
        ...,
        description=(
            "Source-owned summary of cross-currency transactions blocked by missing "
            "historical FX prerequisites."
        ),
    )


class CalculatorSloBucket(BaseModel):
    pending_jobs: int = Field(
        ...,
        description="Count of jobs currently waiting in PENDING state.",
        examples=[12],
    )
    processing_jobs: int = Field(
        ...,
        description="Count of jobs actively processing.",
        examples=[3],
    )
    stale_processing_jobs: int = Field(
        ...,
        description="Count of PROCESSING jobs older than stale threshold (15 minutes).",
        examples=[1],
    )
    failed_jobs: int = Field(
        ...,
        description="Count of jobs currently in FAILED terminal state.",
        examples=[0],
    )
    failed_jobs_within_window: int = Field(
        ...,
        description=(
            "Count of jobs that moved to FAILED state within the configured failed-job window."
        ),
        examples=[2],
    )
    oldest_open_job_date: Optional[date] = Field(
        None,
        description="Oldest business date among open jobs (PENDING/PROCESSING).",
        examples=["2026-02-25"],
    )
    oldest_open_job_id: Optional[int] = Field(
        None,
        description="Durable job id for the oldest open job contributing to this backlog.",
        examples=[8801],
    )
    oldest_open_job_correlation_id: Optional[str] = Field(
        None,
        description=(
            "Durable correlation identifier for the oldest open job contributing to this backlog."
        ),
        examples=["corr-val-20260313-001"],
    )
    backlog_age_days: Optional[int] = Field(
        None,
        description=(
            "Age in days from oldest_open_job_date to business_date "
            "(or current UTC date when business_date is unavailable)."
        ),
        examples=[7],
    )


class ReprocessingSloBucket(BaseModel):
    active_reprocessing_keys: int = Field(
        ...,
        description="Number of position keys currently in REPROCESSING state.",
        examples=[4],
    )
    stale_reprocessing_keys: int = Field(
        ...,
        description=(
            "Number of REPROCESSING position keys whose last update is older than the stale "
            "threshold."
        ),
        examples=[1],
    )
    oldest_reprocessing_watermark_date: Optional[date] = Field(
        None,
        description="Oldest watermark date among position keys currently in REPROCESSING state.",
        examples=["2026-02-25"],
    )
    oldest_reprocessing_security_id: Optional[str] = Field(
        None,
        description="Security identifier for the oldest active reprocessing key.",
        examples=["AAPL"],
    )
    oldest_reprocessing_epoch: Optional[int] = Field(
        None,
        description="Current epoch of the oldest active reprocessing key.",
        examples=[3],
    )
    oldest_reprocessing_updated_at: Optional[datetime] = Field(
        None,
        description=(
            "UTC timestamp of the most recent durable update for the oldest active "
            "reprocessing key."
        ),
        examples=["2026-03-13T10:15:09Z"],
    )
    backlog_age_days: Optional[int] = Field(
        None,
        description=(
            "Age in days from oldest_reprocessing_watermark_date to business_date "
            "(or current UTC date when business_date is unavailable)."
        ),
        examples=[7],
    )


class CalculatorSloResponse(BaseModel):
    portfolio_id: str = Field(..., description="Unique portfolio identifier.", examples=["PF-001"])
    business_date: Optional[date] = Field(
        None,
        description="Latest business date from default business calendar.",
        examples=["2026-03-02"],
    )
    stale_threshold_minutes: int = Field(
        ...,
        description="Threshold used to classify stale processing jobs.",
        examples=[15],
    )
    failed_window_hours: int = Field(
        ...,
        description=CALCULATOR_SLO_FAILED_WINDOW_DESCRIPTION,
        examples=[24],
    )
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this SLO snapshot was generated.",
        examples=["2026-03-03T10:05:11Z"],
    )
    valuation: CalculatorSloBucket = Field(
        ...,
        description="Valuation calculator SLO snapshot for this portfolio.",
        examples=[
            {
                "pending_jobs": 12,
                "processing_jobs": 3,
                "stale_processing_jobs": 1,
                "failed_jobs": 0,
                "failed_jobs_within_window": 2,
                "oldest_open_job_date": "2026-02-25",
                "oldest_open_job_id": 8801,
                "oldest_open_job_correlation_id": "corr-val-20260313-001",
                "backlog_age_days": 7,
            }
        ],
    )
    aggregation: CalculatorSloBucket = Field(
        ...,
        description="Timeseries aggregation SLO snapshot for this portfolio.",
        examples=[
            {
                "pending_jobs": 1,
                "processing_jobs": 0,
                "stale_processing_jobs": 0,
                "failed_jobs": 0,
                "failed_jobs_within_window": 0,
                "oldest_open_job_date": "2026-03-01",
                "oldest_open_job_id": 4402,
                "oldest_open_job_correlation_id": "corr-agg-20260313-001",
                "backlog_age_days": 1,
            }
        ],
    )
    reprocessing: ReprocessingSloBucket = Field(
        ...,
        description="Reprocessing SLO snapshot for this portfolio.",
        examples=[
            {
                "active_reprocessing_keys": 4,
                "stale_reprocessing_keys": 1,
                "oldest_reprocessing_watermark_date": "2026-02-25",
                "oldest_reprocessing_security_id": "AAPL",
                "oldest_reprocessing_epoch": 3,
                "oldest_reprocessing_updated_at": "2026-03-13T10:15:09Z",
                "backlog_age_days": 7,
            }
        ],
    )


class LineageResponse(BaseModel):
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this lineage snapshot was generated.",
        examples=["2026-03-14T10:45:00Z"],
    )
    portfolio_id: str = Field(..., description="Unique portfolio identifier.", examples=["PF-001"])
    security_id: str = Field(..., description="Unique security identifier.", examples=["AAPL.OQ"])
    epoch: int = Field(..., description="Current active epoch for this key.", examples=[3])
    watermark_date: date = Field(
        ...,
        description="Watermark date from which replay/reprocessing is active.",
        examples=["2025-11-01"],
    )
    reprocessing_status: str = Field(
        ..., description="Current status for this key.", examples=["CURRENT", "REPROCESSING"]
    )
    latest_position_history_date: Optional[date] = Field(
        None,
        description="Latest date available in position_history for current epoch.",
        examples=["2025-12-30"],
    )
    latest_daily_snapshot_date: Optional[date] = Field(
        None,
        description="Latest date available in daily_position_snapshots for current epoch.",
        examples=["2025-12-30"],
    )
    latest_valuation_job_date: Optional[date] = Field(
        None,
        description="Latest valuation job business date for current epoch.",
        examples=["2025-12-30"],
    )
    latest_valuation_job_id: Optional[int] = Field(
        None,
        description="Durable database identifier of the latest valuation job in the current epoch.",
        examples=[101],
    )
    latest_valuation_job_status: Optional[str] = Field(
        None,
        description="Status of the latest valuation job for current epoch.",
        examples=["PENDING", "PROCESSING", "COMPLETE", "FAILED"],
    )
    latest_valuation_job_correlation_id: Optional[str] = Field(
        None,
        description=(
            "Durable correlation identifier of the latest valuation job in the current epoch, "
            "used to bridge lineage triage to logs and scheduler dispatch."
        ),
        examples=["corr-val-20260314-001"],
    )
    has_artifact_gap: bool = Field(
        ...,
        description=(
            "True when the current epoch shows missing or lagging downstream artifacts relative "
            "to the latest position history for this key."
        ),
        examples=[False, True],
    )
    operational_state: str = Field(
        ...,
        description=(
            "Derived operator-facing lineage state for this key, based on replay status and "
            "artifact freshness."
        ),
        examples=["HEALTHY", "REPLAYING", "ARTIFACT_GAP", "VALUATION_BLOCKED"],
    )


class LineageKeyRecord(BaseModel):
    security_id: str = Field(
        ..., description="Security identifier for the key.", examples=["AAPL.OQ"]
    )
    epoch: int = Field(..., description="Current active epoch for this key.", examples=[3])
    watermark_date: date = Field(
        ...,
        description="Current watermark date for replay/reprocessing on this key.",
        examples=["2025-11-01"],
    )
    reprocessing_status: str = Field(
        ...,
        description="Current key status.",
        examples=["CURRENT", "REPROCESSING"],
    )
    latest_position_history_date: Optional[date] = Field(
        None,
        description="Latest position-history date for the current epoch of this key.",
        examples=["2025-12-30"],
    )
    latest_daily_snapshot_date: Optional[date] = Field(
        None,
        description="Latest daily snapshot date for the current epoch of this key.",
        examples=["2025-12-30"],
    )
    latest_valuation_job_date: Optional[date] = Field(
        None,
        description=(
            "Latest valuation job business date recorded for the current epoch of this key."
        ),
        examples=["2025-12-30"],
    )
    latest_valuation_job_id: Optional[int] = Field(
        None,
        description="Durable database identifier of the latest valuation job in the current epoch.",
        examples=[101],
    )
    latest_valuation_job_status: Optional[str] = Field(
        None,
        description=(
            "Status of the latest valuation job recorded for the current epoch of this key."
        ),
        examples=["PENDING", "PROCESSING", "COMPLETE", "FAILED"],
    )
    latest_valuation_job_correlation_id: Optional[str] = Field(
        None,
        description=(
            "Durable correlation identifier of the latest valuation job in the current epoch, "
            "used to bridge lineage triage to logs and scheduler dispatch."
        ),
        examples=["corr-val-20260314-001"],
    )
    has_artifact_gap: bool = Field(
        ...,
        description=(
            "True when the current epoch shows missing or lagging downstream artifacts relative "
            "to the latest position history for this key."
        ),
        examples=[False, True],
    )
    operational_state: str = Field(
        ...,
        description=(
            "Derived operator-facing lineage state for this key, based on replay status and "
            "artifact freshness."
        ),
        examples=["HEALTHY", "REPLAYING", "ARTIFACT_GAP", "VALUATION_BLOCKED"],
    )


class LineageKeyListResponse(BaseModel):
    product_name: Literal["IngestionEvidenceBundle"] = product_name_field("IngestionEvidenceBundle")
    product_version: Literal["v1"] = product_version_field()
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this lineage key snapshot was generated.",
        examples=["2026-03-14T10:45:00Z"],
    )
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    total: int = Field(..., description="Total matching keys for this portfolio.", examples=[24])
    skip: int = Field(..., description="Pagination offset.", examples=[0])
    limit: int = Field(..., description="Pagination limit.", examples=[50])
    items: list[LineageKeyRecord] = Field(
        ...,
        description="Current lineage key states.",
        examples=[
            [
                {
                    "security_id": "AAPL.OQ",
                    "epoch": 3,
                    "watermark_date": "2025-11-01",
                    "reprocessing_status": "CURRENT",
                    "latest_position_history_date": "2025-12-30",
                    "latest_daily_snapshot_date": "2025-12-30",
                    "latest_valuation_job_date": "2025-12-30",
                    "latest_valuation_job_id": 101,
                    "latest_valuation_job_status": "COMPLETE",
                    "latest_valuation_job_correlation_id": "corr-val-20260314-001",
                    "has_artifact_gap": False,
                    "operational_state": "HEALTHY",
                }
            ]
        ],
    )


class SupportJobRecord(BaseModel):
    job_id: int = Field(
        ...,
        description="Durable database identifier for this job row.",
        examples=[101],
    )
    job_type: Literal["VALUATION", "AGGREGATION", "RESET_WATERMARKS"] = Field(
        ...,
        description=(
            "Type of support job. RESET_WATERMARKS represents a durable replay job used to "
            "reset watermarks for valuation/timeseries recomputation."
        ),
        examples=["VALUATION", "RESET_WATERMARKS"],
    )
    business_date: date = Field(
        ...,
        description="Business date for the job (valuation_date or aggregation_date).",
        examples=["2025-12-30"],
    )
    status: str = Field(
        ..., description="Current job status.", examples=["PENDING", "PROCESSING", "COMPLETE"]
    )
    security_id: Optional[str] = Field(
        None,
        description=(
            "Security identifier for security-scoped work such as valuation or durable replay jobs."
        ),
        examples=["AAPL.OQ", "SEC-US-IBM"],
    )
    epoch: Optional[int] = Field(
        None,
        description="Epoch for valuation jobs when the support row is epoch-scoped.",
        examples=[3],
    )
    attempt_count: Optional[int] = Field(
        None,
        description="Current retry attempt count for valuation jobs.",
        examples=[1],
    )
    is_retrying: bool = Field(
        ...,
        description=(
            "True when the durable job has already consumed at least one retry attempt and is "
            "still awaiting terminal completion."
        ),
        examples=[False],
    )
    correlation_id: Optional[str] = Field(
        None,
        description=(
            "Durable correlation identifier captured when the job was created, used to join "
            "support triage with logs, events, and replay lineage."
        ),
        examples=["corr-valuation-20260313-001"],
    )
    created_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp when the durable job row was first created.",
        examples=["2026-03-13T10:10:00Z"],
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp of the most recent durable lifecycle update for the job.",
        examples=["2026-03-13T10:15:09Z"],
    )
    is_stale_processing: bool = Field(
        ...,
        description=(
            "True when the job is in PROCESSING state and its last update is older than the "
            "support stale threshold (15 minutes)."
        ),
        examples=[False],
    )
    failure_reason: Optional[str] = Field(
        None,
        description="Failure reason (when status=FAILED).",
        examples=["Missing market price for security/date"],
    )
    is_terminal_failure: bool = Field(
        ...,
        description="True when the durable job is in FAILED terminal state.",
        examples=[False, True],
    )
    operational_state: Literal[
        "FAILED",
        "SKIPPED",
        "STALE_PROCESSING",
        "PROCESSING",
        "PENDING",
        "COMPLETED",
    ] = Field(
        ...,
        description=("Derived operator-facing lifecycle state used for support triage ordering."),
        examples=["STALE_PROCESSING", "SKIPPED"],
    )


class SupportJobListResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    stale_threshold_minutes: int = Field(
        ...,
        description="Threshold in minutes used to classify stale support rows in this listing.",
        examples=[15],
    )
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this support job listing snapshot was generated.",
        examples=["2026-03-14T10:50:00Z"],
    )
    total: int = Field(..., description="Total jobs matching the filter.", examples=[42])
    skip: int = Field(..., description="Pagination offset.", examples=[0])
    limit: int = Field(..., description="Pagination limit.", examples=[50])
    items: list[SupportJobRecord] = Field(
        ...,
        description="Operational jobs for support workflows.",
        examples=[
            [
                {
                    "job_id": 101,
                    "job_type": "VALUATION",
                    "business_date": "2025-12-30",
                    "status": "PENDING",
                    "security_id": "AAPL.OQ",
                    "epoch": 3,
                    "attempt_count": 1,
                    "is_retrying": True,
                    "correlation_id": "corr-valuation-20260313-001",
                    "created_at": "2025-12-30T10:10:00Z",
                    "updated_at": "2025-12-30T10:15:09Z",
                    "is_stale_processing": False,
                    "failure_reason": None,
                    "is_terminal_failure": False,
                    "operational_state": "PENDING",
                }
            ]
        ],
    )


class ReprocessingJobListResponse(SupportJobListResponse):
    product_name: Literal["IngestionEvidenceBundle"] = product_name_field("IngestionEvidenceBundle")
    product_version: Literal["v1"] = product_version_field()


class AnalyticsExportJobRecord(BaseModel):
    job_id: str = Field(
        ...,
        description="Stable analytics export job identifier.",
        examples=["aexp_1234567890abcdef"],
    )
    request_fingerprint: str = Field(
        ...,
        description=(
            "Stable deduplication fingerprint for the export request, used to correlate reuse "
            "or stale supersession behavior."
        ),
        examples=["fp_portfolio_timeseries_pf001_20260313_v1"],
    )
    dataset_type: str = Field(
        ..., description="Analytics dataset exported by the job.", examples=["portfolio_timeseries"]
    )
    status: str = Field(
        ..., description="Current analytics export job status.", examples=["running"]
    )
    created_at: datetime = Field(
        ...,
        description="UTC timestamp when the export job was created.",
        examples=["2026-03-13T10:15:00Z"],
    )
    started_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp when export processing started.",
        examples=["2026-03-13T10:15:01Z"],
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp when export processing completed or failed.",
        examples=["2026-03-13T10:15:09Z"],
    )
    updated_at: datetime = Field(
        ...,
        description="UTC timestamp of the most recent durable lifecycle update for the export job.",
        examples=["2026-03-13T10:17:00Z"],
    )
    is_stale_running: bool = Field(
        ...,
        description=(
            "True when the export job is in RUNNING state and its last update is older than the "
            "support stale threshold (15 minutes)."
        ),
        examples=[False],
    )
    backlog_age_minutes: Optional[int] = Field(
        None,
        description=(
            "Age in minutes from created_at to the current UTC time while the job remains in "
            "ACCEPTED or RUNNING state."
        ),
        examples=[42],
    )
    result_row_count: Optional[int] = Field(
        None,
        description="Number of rows emitted when the export completed successfully.",
        examples=[365],
    )
    error_message: Optional[str] = Field(
        None,
        description="Failure reason when the export job reaches FAILED state.",
        examples=["Missing FX rate for EUR/USD on 2025-01-31."],
    )
    is_terminal_failure: bool = Field(
        ...,
        description="True when the export job is durably in FAILED terminal state.",
        examples=[True],
    )
    operational_state: Literal[
        "FAILED",
        "STALE_RUNNING",
        "RUNNING",
        "ACCEPTED",
        "COMPLETED",
    ] = Field(
        ...,
        description="Derived operator-facing lifecycle state used for support triage ordering.",
        examples=["FAILED"],
    )


class AnalyticsExportJobListResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    stale_threshold_minutes: int = Field(
        ...,
        description="Threshold in minutes used to classify stale support rows in this listing.",
        examples=[15],
    )
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this analytics export listing snapshot was generated.",
        examples=["2026-03-14T10:50:00Z"],
    )
    total: int = Field(..., description="Total export jobs matching the filter.", examples=[12])
    skip: int = Field(..., description="Pagination offset.", examples=[0])
    limit: int = Field(..., description="Pagination limit.", examples=[50])
    items: list[AnalyticsExportJobRecord] = Field(
        ...,
        description="Durable analytics export jobs for support workflows.",
        examples=[
            [
                {
                    "job_id": "aexp_1234567890abcdef",
                    "request_fingerprint": "fp_portfolio_timeseries_pf001_20260313_v1",
                    "dataset_type": "portfolio_timeseries",
                    "status": "failed",
                    "created_at": "2026-03-13T10:15:00Z",
                    "started_at": "2026-03-13T10:15:01Z",
                    "completed_at": "2026-03-13T10:15:02Z",
                    "updated_at": "2026-03-13T10:15:02Z",
                    "is_stale_running": False,
                    "backlog_age_minutes": None,
                    "result_row_count": None,
                    "error_message": "Unexpected analytics export processing failure.",
                    "is_terminal_failure": True,
                    "operational_state": "FAILED",
                }
            ]
        ],
    )


class ReconciliationRunRecord(BaseModel):
    run_id: str = Field(
        ...,
        description="Stable financial reconciliation run identifier.",
        examples=["recon_1234567890abcdef"],
    )
    reconciliation_type: str = Field(
        ...,
        description="Control family executed by the run.",
        examples=["transaction_cashflow"],
    )
    status: str = Field(
        ...,
        description="Current reconciliation run status.",
        examples=["COMPLETED"],
    )
    business_date: Optional[date] = Field(
        None,
        description="Business date scope for the reconciliation run.",
        examples=["2026-03-13"],
    )
    epoch: Optional[int] = Field(
        None,
        description="Epoch scope for the reconciliation run when applicable.",
        examples=[3],
    )
    started_at: datetime = Field(
        ...,
        description="UTC timestamp when reconciliation execution started.",
        examples=["2026-03-13T10:15:00Z"],
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp when reconciliation execution completed.",
        examples=["2026-03-13T10:15:09Z"],
    )
    requested_by: Optional[str] = Field(
        None,
        description="Principal or subsystem that requested the reconciliation run.",
        examples=["support.ops@lotus.local", "pipeline_orchestrator_service"],
    )
    dedupe_key: Optional[str] = Field(
        None,
        description=(
            "Stable deduplication key for the run when the control path enforces one-run-per-scope "
            "behavior."
        ),
        examples=["recon:transaction_cashflow:PF-001:2026-03-13:3"],
    )
    correlation_id: Optional[str] = Field(
        None,
        description=(
            "Durable correlation identifier captured for the reconciliation run, used to join "
            "support triage with logs and upstream control requests."
        ),
        examples=["corr-recon-20260313-001"],
    )
    failure_reason: Optional[str] = Field(
        None,
        description="Failure reason when the reconciliation run reaches FAILED state.",
        examples=["Tolerance exceeded for portfolio timeseries totals."],
    )
    is_terminal_failure: bool = Field(
        ...,
        description="True when the reconciliation run is durably in FAILED terminal state.",
        examples=[True],
    )
    is_blocking: bool = Field(
        ...,
        description=(
            "True when the run status blocks downstream publication or release decisions "
            "(FAILED or REQUIRES_REPLAY)."
        ),
        examples=[True],
    )
    operational_state: Literal["BLOCKING", "RUNNING", "COMPLETED"] = Field(
        ...,
        description="Derived operator-facing lifecycle state used for support triage ordering.",
        examples=["BLOCKING"],
    )


class ReconciliationRunListResponse(BaseModel):
    product_name: Literal["ReconciliationEvidenceBundle"] = product_name_field(
        "ReconciliationEvidenceBundle"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this reconciliation-run support snapshot was generated.",
        examples=["2026-03-14T10:50:00Z"],
    )
    total: int = Field(
        ..., description="Total reconciliation runs matching the filter.", examples=[8]
    )
    skip: int = Field(..., description="Pagination offset.", examples=[0])
    limit: int = Field(..., description="Pagination limit.", examples=[50])
    items: list[ReconciliationRunRecord] = Field(
        ...,
        description="Durable reconciliation runs for support workflows.",
        examples=[
            [
                {
                    "run_id": "recon_1234567890abcdef",
                    "reconciliation_type": "transaction_cashflow",
                    "status": "COMPLETED",
                    "business_date": "2026-03-13",
                    "epoch": 3,
                    "started_at": "2026-03-13T10:15:00Z",
                    "completed_at": "2026-03-13T10:15:09Z",
                    "requested_by": "pipeline_orchestrator_service",
                    "dedupe_key": "recon:transaction_cashflow:PF-001:2026-03-13:3",
                    "correlation_id": "corr-recon-20260313-001",
                    "failure_reason": None,
                    "is_terminal_failure": False,
                    "is_blocking": False,
                    "operational_state": "COMPLETED",
                }
            ]
        ],
    )


class ReconciliationFindingRecord(BaseModel):
    finding_id: str = Field(
        ...,
        description="Stable reconciliation finding identifier.",
        examples=["rf_1234567890abcdef"],
    )
    finding_type: str = Field(
        ...,
        description="Canonical reconciliation finding type.",
        examples=["missing_cashflow"],
    )
    severity: str = Field(
        ...,
        description="Operational severity assigned to the finding.",
        examples=["ERROR"],
    )
    security_id: Optional[str] = Field(
        None,
        description="Security identifier affected by the finding, when applicable.",
        examples=["SEC-US-IBM"],
    )
    transaction_id: Optional[str] = Field(
        None,
        description="Transaction identifier affected by the finding, when applicable.",
        examples=["TXN-20260313-0042"],
    )
    business_date: Optional[date] = Field(
        None,
        description="Business date evaluated by the control.",
        examples=["2026-03-13"],
    )
    epoch: Optional[int] = Field(
        None,
        description="Epoch evaluated by the control when applicable.",
        examples=[3],
    )
    created_at: datetime = Field(
        ...,
        description="UTC timestamp when the finding was persisted.",
        examples=["2026-03-13T10:15:09Z"],
    )
    detail: Optional[dict[str, Any]] = Field(
        None,
        description="Structured detail describing the mismatch or control breach.",
        examples=[{"expected_cashflow_count": 1, "observed_cashflow_count": 0}],
    )
    is_blocking: bool = Field(
        ...,
        description=(
            "True when the finding represents a publication-blocking control breach "
            "(currently severity ERROR)."
        ),
        examples=[True, False],
    )
    operational_state: Literal["BLOCKING", "NON_BLOCKING"] = Field(
        ...,
        description="Derived operator-facing state for support triage of reconciliation findings.",
        examples=["BLOCKING"],
    )


class ReconciliationFindingListResponse(BaseModel):
    product_name: Literal["ReconciliationEvidenceBundle"] = product_name_field(
        "ReconciliationEvidenceBundle"
    )
    product_version: Literal["v1"] = product_version_field()
    run_id: str = Field(
        ..., description="Reconciliation run identifier.", examples=["recon_1234567890abcdef"]
    )
    generated_at_utc: datetime = Field(
        ...,
        description=(
            "UTC timestamp when this reconciliation-finding support snapshot was generated."
        ),
        examples=["2026-03-14T10:50:00Z"],
    )
    total: int = Field(..., description="Total findings returned for the run.", examples=[2])
    items: list[ReconciliationFindingRecord] = Field(
        ...,
        description="Durable reconciliation findings for the requested run.",
        examples=[
            [
                {
                    "finding_id": "rf_1234567890abcdef",
                    "finding_type": "missing_cashflow",
                    "severity": "ERROR",
                    "security_id": "SEC-US-IBM",
                    "transaction_id": "TXN-20260313-0042",
                    "business_date": "2026-03-13",
                    "epoch": 3,
                    "created_at": "2026-03-13T10:15:09Z",
                    "detail": {"expected_cashflow_count": 1, "observed_cashflow_count": 0},
                    "is_blocking": True,
                    "operational_state": "BLOCKING",
                }
            ]
        ],
    )


class PortfolioControlStageRecord(BaseModel):
    stage_id: int = Field(
        ...,
        description="Durable database identifier for this portfolio control stage row.",
        examples=[701],
    )
    stage_name: str = Field(
        ...,
        description="Control-plane stage name recorded for the portfolio-day scope.",
        examples=["FINANCIAL_RECONCILIATION"],
    )
    business_date: date = Field(
        ...,
        description="Business date covered by the durable portfolio control stage row.",
        examples=["2026-03-13"],
    )
    epoch: int = Field(
        ...,
        description="Epoch of the portfolio-day control stage row.",
        examples=[3],
    )
    status: str = Field(
        ...,
        description="Current durable control stage status.",
        examples=["REQUIRES_REPLAY"],
    )
    last_source_event_type: Optional[str] = Field(
        None,
        description="Last event type that updated the control stage row.",
        examples=["portfolio_day.reconciliation.completed"],
    )
    created_at: datetime = Field(
        ...,
        description="UTC timestamp when the durable control stage row was first created.",
        examples=["2026-03-13T10:10:00Z"],
    )
    ready_emitted_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp when the control stage emitted downstream readiness, if any.",
        examples=["2026-03-13T10:14:30Z"],
    )
    updated_at: datetime = Field(
        ...,
        description=(
            "UTC timestamp of the most recent durable lifecycle update for the control stage."
        ),
        examples=["2026-03-13T10:15:09Z"],
    )
    is_blocking: bool = Field(
        ...,
        description=(
            "True when the control stage blocks downstream publication or release decisions."
        ),
        examples=[True],
    )
    operational_state: Literal["BLOCKING", "COMPLETED"] = Field(
        ...,
        description="Derived operator-facing lifecycle state used for support triage ordering.",
        examples=["BLOCKING"],
    )


class PortfolioControlStageListResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this control-stage support snapshot was generated.",
        examples=["2026-03-14T10:50:00Z"],
    )
    total: int = Field(
        ..., description="Total portfolio control stage rows matching the filter.", examples=[6]
    )
    skip: int = Field(..., description="Pagination offset.", examples=[0])
    limit: int = Field(..., description="Pagination limit.", examples=[50])
    items: list[PortfolioControlStageRecord] = Field(
        ...,
        description="Durable portfolio-day control stage rows for support workflows.",
        examples=[
            [
                {
                    "stage_id": 701,
                    "stage_name": "FINANCIAL_RECONCILIATION",
                    "business_date": "2026-03-13",
                    "epoch": 3,
                    "status": "REQUIRES_REPLAY",
                    "last_source_event_type": "portfolio_day.reconciliation.completed",
                    "created_at": "2026-03-13T10:10:00Z",
                    "ready_emitted_at": None,
                    "updated_at": "2026-03-13T10:15:09Z",
                    "is_blocking": True,
                    "operational_state": "BLOCKING",
                }
            ]
        ],
    )


class ReprocessingKeyRecord(BaseModel):
    security_id: str = Field(
        ...,
        description="Security identifier for the durable portfolio-security replay key.",
        examples=["SEC-US-IBM"],
    )
    epoch: int = Field(
        ...,
        description="Current active epoch for the replay key.",
        examples=[3],
    )
    watermark_date: date = Field(
        ...,
        description="Current replay watermark date for the portfolio-security key.",
        examples=["2026-03-10"],
    )
    status: str = Field(
        ...,
        description="Current durable reprocessing state for the key.",
        examples=["REPROCESSING"],
    )
    created_at: datetime = Field(
        ...,
        description="UTC timestamp when the durable replay key row was first created.",
        examples=["2026-03-13T10:05:00Z"],
    )
    updated_at: datetime = Field(
        ...,
        description="UTC timestamp of the most recent durable lifecycle update for the key.",
        examples=["2026-03-13T10:15:09Z"],
    )
    is_stale_reprocessing: bool = Field(
        ...,
        description=(
            "True when the key is still marked REPROCESSING and its last durable update is older "
            "than the support stale threshold (15 minutes)."
        ),
        examples=[False],
    )
    operational_state: Literal["STALE_REPROCESSING", "REPROCESSING", "CURRENT"] = Field(
        ...,
        description="Derived operator-facing lifecycle state used for support triage ordering.",
        examples=["REPROCESSING"],
    )


class ReprocessingKeyListResponse(BaseModel):
    product_name: Literal["IngestionEvidenceBundle"] = product_name_field("IngestionEvidenceBundle")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    stale_threshold_minutes: int = Field(
        ...,
        description="Threshold in minutes used to classify stale support rows in this listing.",
        examples=[15],
    )
    generated_at_utc: datetime = Field(
        ...,
        description="UTC timestamp when this replay-key listing snapshot was generated.",
        examples=["2026-03-14T10:50:00Z"],
    )
    total: int = Field(
        ...,
        description="Total durable portfolio-security replay keys matching the filter.",
        examples=[4],
    )
    skip: int = Field(..., description="Pagination offset.", examples=[0])
    limit: int = Field(..., description="Pagination limit.", examples=[100])
    items: list[ReprocessingKeyRecord] = Field(
        ...,
        description="Durable replay key rows for support workflows.",
        examples=[
            [
                {
                    "security_id": "SEC-US-IBM",
                    "epoch": 3,
                    "watermark_date": "2026-03-10",
                    "status": "REPROCESSING",
                    "created_at": "2026-03-13T10:05:00Z",
                    "updated_at": "2026-03-13T10:15:09Z",
                    "is_stale_reprocessing": False,
                    "operational_state": "REPROCESSING",
                }
            ]
        ],
    )
