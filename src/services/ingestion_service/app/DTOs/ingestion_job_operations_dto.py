from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

IngestionJobStatus = Literal["accepted", "queued", "failed"]


class IngestionHealthSummaryResponse(BaseModel):
    total_jobs: int = Field(
        ge=0,
        description="Total ingestion jobs stored in operational state.",
        examples=[2450],
    )
    accepted_jobs: int = Field(
        ge=0,
        description="Total jobs currently in accepted state.",
        examples=[3],
    )
    queued_jobs: int = Field(
        ge=0,
        description="Total jobs currently queued for asynchronous processing.",
        examples=[7],
    )
    failed_jobs: int = Field(
        ge=0,
        description="Total jobs currently marked as failed.",
        examples=[2],
    )
    backlog_jobs: int = Field(
        ge=0,
        description="Operational backlog count (accepted + queued).",
        examples=[10],
    )
    oldest_backlog_job_id: str | None = Field(
        default=None,
        description="Identifier of the oldest non-terminal job contributing to the backlog.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )


class IngestionSloStatusResponse(BaseModel):
    lookback_minutes: int = Field(
        ge=1,
        description="Lookback window in minutes used for SLO calculations.",
        examples=[60],
    )
    total_jobs: int = Field(
        ge=0,
        description="Number of jobs observed in the lookback window.",
        examples=[320],
    )
    failed_jobs: int = Field(
        ge=0,
        description="Number of failed jobs observed in the lookback window.",
        examples=[4],
    )
    failure_rate: Decimal = Field(
        ge=Decimal("0"),
        description="Failed jobs divided by total jobs in the lookback window.",
        examples=["0.0125"],
    )
    p95_queue_latency_seconds: float = Field(
        ge=0.0,
        description="95th percentile latency from job submission to queue completion.",
        examples=[1.42],
    )
    backlog_age_seconds: float = Field(
        ge=0.0,
        description="Age in seconds of the oldest non-terminal ingestion job.",
        examples=[74.0],
    )
    breach_failure_rate: bool = Field(
        description="Whether failure rate exceeds configured threshold.",
        examples=[False],
    )
    breach_queue_latency: bool = Field(
        description="Whether p95 queue latency exceeds configured threshold.",
        examples=[False],
    )
    breach_backlog_age: bool = Field(
        description="Whether backlog age exceeds configured threshold.",
        examples=[False],
    )


class IngestionOperatingBandResponse(BaseModel):
    lookback_minutes: int = Field(
        ge=1,
        description="Lookback window in minutes used for operating-band classification.",
        examples=[60],
    )
    operating_band: Literal["green", "yellow", "orange", "red"] = Field(
        description=(
            "Current operating severity band for ingestion and calculator scaling workflows."
        ),
        examples=["yellow"],
    )
    recommended_action: str = Field(
        description="Runbook-oriented next action for this band.",
        examples=["Scale up one band and monitor DLQ pressure."],
    )
    backlog_age_seconds: float = Field(
        ge=0.0,
        description="Oldest non-terminal ingestion backlog age used for band classification.",
        examples=[42.0],
    )
    dlq_pressure_ratio: Decimal = Field(
        ge=Decimal("0"),
        description="DLQ pressure ratio used for band classification.",
        examples=["0.3000"],
    )
    failure_rate: Decimal = Field(
        ge=Decimal("0"),
        description="Current failure rate used for band classification.",
        examples=["0.0125"],
    )
    triggered_signals: list[str] = Field(
        description="List of signals that triggered the final band decision.",
        examples=[["backlog_age_seconds>=15", "dlq_pressure_ratio>=0.25"]],
    )


class IngestionOpsPolicyResponse(BaseModel):
    policy_version: str = Field(
        description="Semantic policy schema/version identifier for ingestion operating policy.",
        examples=["v1"],
    )
    policy_fingerprint: str = Field(
        description="Deterministic fingerprint of active policy values for drift detection.",
        examples=["e6a9f2cc3bb5e5a7"],
    )
    lookback_minutes_default: int = Field(
        ge=1,
        description="Default lookback window (minutes) used by ingestion health endpoints.",
        examples=[60],
    )
    failure_rate_threshold_default: Decimal = Field(
        ge=Decimal("0"),
        description="Default failure-rate threshold used for SLO/error-budget evaluations.",
        examples=["0.03"],
    )
    queue_latency_threshold_seconds_default: float = Field(
        ge=0.0,
        description="Default queue-latency threshold (seconds) used for SLO evaluation.",
        examples=[5.0],
    )
    backlog_age_threshold_seconds_default: float = Field(
        ge=0.0,
        description="Default backlog-age threshold (seconds) used for SLO evaluation.",
        examples=[300.0],
    )
    replay_max_records_per_request: int = Field(
        ge=1,
        description="Replay guardrail: maximum replay records allowed per request.",
        examples=[5000],
    )
    replay_max_backlog_jobs: int = Field(
        ge=1,
        description="Replay guardrail: backlog ceiling beyond which replay is blocked.",
        examples=[5000],
    )
    reprocessing_worker_poll_interval_seconds: int = Field(
        ge=1,
        description="Configured poll interval (seconds) for the valuation reprocessing worker.",
        examples=[10],
    )
    reprocessing_worker_batch_size: int = Field(
        ge=1,
        description="Configured batch size used by the valuation reprocessing worker claim loop.",
        examples=[10],
    )
    valuation_scheduler_poll_interval_seconds: int = Field(
        ge=1,
        description="Configured poll interval (seconds) for the valuation scheduler.",
        examples=[30],
    )
    valuation_scheduler_batch_size: int = Field(
        ge=1,
        description="Configured batch size for valuation scheduler scans and claims.",
        examples=[100],
    )
    valuation_scheduler_dispatch_rounds: int = Field(
        ge=1,
        description="Configured number of dispatch claim rounds executed per scheduler poll.",
        examples=[10],
    )
    dlq_budget_events_per_window: int = Field(
        ge=1,
        description="DLQ budget used to compute DLQ pressure ratios for the active window.",
        examples=[10],
    )
    operating_band_yellow_backlog_age_seconds: float = Field(
        ge=0.0,
        description="Backlog age threshold (seconds) that triggers yellow operating band.",
        examples=[15.0],
    )
    operating_band_orange_backlog_age_seconds: float = Field(
        ge=0.0,
        description="Backlog age threshold (seconds) that triggers orange operating band.",
        examples=[60.0],
    )
    operating_band_red_backlog_age_seconds: float = Field(
        ge=0.0,
        description="Backlog age threshold (seconds) that triggers red operating band.",
        examples=[180.0],
    )
    operating_band_yellow_dlq_pressure_ratio: Decimal = Field(
        ge=Decimal("0"),
        description="DLQ pressure threshold that triggers yellow operating band.",
        examples=["0.25"],
    )
    operating_band_orange_dlq_pressure_ratio: Decimal = Field(
        ge=Decimal("0"),
        description="DLQ pressure threshold that triggers orange operating band.",
        examples=["0.50"],
    )
    operating_band_red_dlq_pressure_ratio: Decimal = Field(
        ge=Decimal("0"),
        description="DLQ pressure threshold that triggers red operating band.",
        examples=["1.0"],
    )
    calculator_peak_lag_age_seconds: dict[str, int] = Field(
        description=(
            "Peak-load lag-age SLO envelope (seconds) by calculator group "
            "(position, cost, valuation, cashflow, timeseries)."
        ),
        examples=[
            {
                "position": 30,
                "cost": 45,
                "valuation": 60,
                "cashflow": 45,
                "timeseries": 120,
            }
        ],
    )
    replay_isolation_mode: Literal["shared_workers", "dedicated_workers"] = Field(
        description=(
            "Replay execution isolation policy. `shared_workers` reuses primary workers; "
            "`dedicated_workers` isolates replay load to dedicated workers."
        ),
        examples=["shared_workers"],
    )
    partition_growth_strategy: Literal["scale_out_only", "pre_shard_large_portfolios"] = Field(
        description=(
            "Kafka partition growth strategy: `scale_out_only` grows topic partitions with "
            "standard rebalancing; "
            "`pre_shard_large_portfolios` reserves extra partitions for hot-key portfolios."
        ),
        examples=["scale_out_only"],
    )
    replay_dry_run_supported: bool = Field(
        description="Whether replay dry-run mode is supported by the active control plane.",
        examples=[True],
    )


class IngestionReprocessingQueueItemResponse(BaseModel):
    job_type: str = Field(
        description="Canonical reprocessing job type.",
        examples=["RESET_WATERMARKS"],
    )
    pending_jobs: int = Field(
        ge=0,
        description="Number of pending jobs for this job type.",
        examples=[14],
    )
    processing_jobs: int = Field(
        ge=0,
        description="Number of currently processing jobs for this job type.",
        examples=[2],
    )
    failed_jobs: int = Field(
        ge=0,
        description="Number of failed jobs for this job type.",
        examples=[1],
    )
    oldest_pending_created_at: datetime | None = Field(
        description="Timestamp of the oldest pending job for this type, if any.",
        examples=["2026-03-03T04:10:11.000Z"],
    )
    oldest_pending_age_seconds: float = Field(
        ge=0,
        description="Age in seconds for the oldest pending job for this type.",
        examples=[127.5],
    )


class IngestionReprocessingQueueHealthResponse(BaseModel):
    as_of: datetime = Field(
        description="UTC timestamp when queue health was computed.",
        examples=["2026-03-03T04:12:20.000Z"],
    )
    total_pending_jobs: int = Field(
        ge=0,
        description="Total number of pending reprocessing jobs across all types.",
        examples=[14],
    )
    total_processing_jobs: int = Field(
        ge=0,
        description="Total number of processing reprocessing jobs across all types.",
        examples=[3],
    )
    total_failed_jobs: int = Field(
        ge=0,
        description="Total number of failed reprocessing jobs across all types.",
        examples=[1],
    )
    queues: list[IngestionReprocessingQueueItemResponse] = Field(
        description="Per-job-type queue health rows sorted by highest pending pressure.",
        examples=[
            [
                {
                    "job_type": "RESET_WATERMARKS",
                    "pending_jobs": 14,
                    "processing_jobs": 2,
                    "failed_jobs": 1,
                    "oldest_pending_created_at": "2026-03-03T04:10:11.000Z",
                    "oldest_pending_age_seconds": 127.5,
                }
            ]
        ],
    )


class IngestionStalledJobResponse(BaseModel):
    job_id: str = Field(
        description="Ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    endpoint: str = Field(
        description="Ingestion endpoint where the stalled job originated.",
        examples=["/ingest/transactions"],
    )
    entity_type: str = Field(
        description="Canonical entity type for the stalled job.",
        examples=["transaction"],
    )
    status: IngestionJobStatus = Field(
        description="Current status of the stalled job.",
        examples=["accepted"],
    )
    submitted_at: datetime = Field(
        description="Timestamp when the stalled job was accepted.",
        examples=["2026-03-01T00:52:01.012Z"],
    )
    queue_age_seconds: float = Field(
        ge=0.0,
        description="Current age in seconds since submission.",
        examples=[723.1],
    )
    retry_count: int = Field(
        ge=0,
        description="Retry attempts recorded for this job.",
        examples=[1],
    )
    suggested_action: str = Field(
        description="Runbook-oriented suggested action for operations.",
        examples=["Investigate consumer lag and retry this job once root cause is resolved."],
    )


class IngestionStalledJobListResponse(BaseModel):
    threshold_seconds: int = Field(
        ge=1,
        description="Stalled-job threshold used to filter jobs.",
        examples=[300],
    )
    total: int = Field(
        ge=0,
        description="Number of stalled jobs returned.",
        examples=[3],
    )
    jobs: list[IngestionStalledJobResponse] = Field(
        description="Jobs older than threshold in accepted or queued state."
    )


class IngestionRetryRequest(BaseModel):
    record_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Optional subset of record keys to replay. Empty list replays full stored payload."
        ),
        examples=[["TXN-2026-000145", "TXN-2026-000146"]],
    )
    dry_run: bool = Field(
        default=False,
        description="When true, validates retry scope without publishing messages.",
        examples=[False],
    )


class IngestionOpsModeResponse(BaseModel):
    mode: Literal["normal", "paused", "drain"] = Field(
        description=(
            "Current ingestion operations mode used to control replay and write-ingress behavior."
        ),
        examples=["normal"],
    )
    replay_window_start: datetime | None = Field(
        default=None,
        description="Start timestamp for allowed retry replay operations.",
        examples=["2026-03-01T00:00:00Z"],
    )
    replay_window_end: datetime | None = Field(
        default=None,
        description="End timestamp for allowed retry replay operations.",
        examples=["2026-03-01T06:00:00Z"],
    )
    updated_by: str | None = Field(
        default=None,
        description="Principal or automation actor who last changed ops mode.",
        examples=["ops_automation"],
    )
    updated_at: datetime = Field(
        description="Timestamp of last ops mode update.",
        examples=["2026-02-28T22:15:07.234Z"],
    )


class IngestionOpsModeUpdateRequest(BaseModel):
    mode: Literal["normal", "paused", "drain"] = Field(
        description="Target ingestion operations mode to apply.",
        examples=["paused"],
    )
    replay_window_start: datetime | None = Field(
        default=None,
        description="Optional replay window start for retry operations.",
        examples=["2026-03-01T00:00:00Z"],
    )
    replay_window_end: datetime | None = Field(
        default=None,
        description="Optional replay window end for retry operations.",
        examples=["2026-03-01T06:00:00Z"],
    )
    updated_by: str | None = Field(
        default=None,
        description="Actor label for audit trail.",
        examples=["ops_automation"],
    )


class IngestionErrorBudgetStatusResponse(BaseModel):
    lookback_minutes: int = Field(
        ge=1,
        description="Current lookback window in minutes.",
        examples=[60],
    )
    previous_lookback_minutes: int = Field(
        ge=1,
        description="Previous lookback window in minutes used for trend comparison.",
        examples=[60],
    )
    total_jobs: int = Field(
        ge=0,
        description="Number of jobs in current lookback window.",
        examples=[320],
    )
    failed_jobs: int = Field(
        ge=0,
        description="Number of failed jobs in current lookback window.",
        examples=[7],
    )
    failure_rate: Decimal = Field(
        ge=Decimal("0"),
        description="Failed jobs divided by total jobs in current lookback window.",
        examples=["0.0219"],
    )
    remaining_error_budget: Decimal = Field(
        ge=Decimal("0"),
        description="Remaining budget to threshold (max(0, threshold - failure_rate)).",
        examples=["0.0081"],
    )
    backlog_jobs: int = Field(
        ge=0,
        description="Current non-terminal backlog jobs.",
        examples=[12],
    )
    previous_backlog_jobs: int = Field(
        ge=0,
        description="Backlog jobs in previous lookback window.",
        examples=[9],
    )
    backlog_growth: int = Field(
        description="Backlog growth compared with previous window.",
        examples=[3],
    )
    replay_backlog_pressure_ratio: Decimal = Field(
        ge=Decimal("0"),
        description=(
            "Backlog saturation ratio against replay guardrail capacity "
            "(backlog_jobs / replay_max_backlog_jobs)."
        ),
        examples=["0.0024"],
    )
    dlq_events_in_window: int = Field(
        ge=0,
        description="Count of consumer DLQ events observed in current lookback window.",
        examples=[4],
    )
    dlq_budget_events_per_window: int = Field(
        ge=1,
        description="Configured DLQ event budget for the same lookback window.",
        examples=[10],
    )
    dlq_pressure_ratio: Decimal = Field(
        ge=Decimal("0"),
        description=(
            "DLQ pressure ratio against budget "
            "(dlq_events_in_window / dlq_budget_events_per_window)."
        ),
        examples=["0.4000"],
    )
    breach_failure_rate: bool = Field(
        description="Whether failure rate exceeds threshold.",
        examples=[False],
    )
    breach_backlog_growth: bool = Field(
        description="Whether backlog growth exceeds threshold.",
        examples=[False],
    )
