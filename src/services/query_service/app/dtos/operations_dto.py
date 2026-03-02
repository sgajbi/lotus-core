from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


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
    active_reprocessing_keys: int = Field(
        ...,
        description="Number of portfolio-security keys currently marked REPROCESSING.",
        examples=[2],
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
        description="Number of PROCESSING valuation jobs older than stale threshold (15 minutes).",
        examples=[1],
    )
    oldest_pending_valuation_date: Optional[date] = Field(
        None,
        description="Oldest valuation date among pending/processing jobs for backlog analysis.",
        examples=["2025-11-03"],
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
    latest_transaction_date: Optional[date] = Field(
        None,
        description="Most recent transaction business date observed for the portfolio (unbounded).",
        examples=["2026-01-05"],
    )
    latest_booked_transaction_date: Optional[date] = Field(
        None,
        description=(
            "Most recent transaction business date observed for the portfolio "
            "up to business_date."
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
            "Most recent daily position snapshot date in the current epoch "
            "up to business_date."
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


class LineageResponse(BaseModel):
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
    latest_valuation_job_status: Optional[str] = Field(
        None,
        description="Status of the latest valuation job for current epoch.",
        examples=["PENDING", "PROCESSING", "DONE", "FAILED"],
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


class LineageKeyListResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    total: int = Field(..., description="Total matching keys for this portfolio.", examples=[24])
    skip: int = Field(..., description="Pagination offset.", examples=[0])
    limit: int = Field(..., description="Pagination limit.", examples=[50])
    items: list[LineageKeyRecord] = Field(..., description="Current lineage key states.")


class SupportJobRecord(BaseModel):
    job_type: Literal["VALUATION", "AGGREGATION"] = Field(
        ..., description="Type of support job.", examples=["VALUATION"]
    )
    business_date: date = Field(
        ...,
        description="Business date for the job (valuation_date or aggregation_date).",
        examples=["2025-12-30"],
    )
    status: str = Field(
        ..., description="Current job status.", examples=["PENDING", "PROCESSING", "DONE"]
    )
    security_id: Optional[str] = Field(
        None,
        description="Security identifier for valuation jobs.",
        examples=["AAPL.OQ"],
    )
    epoch: Optional[int] = Field(
        None,
        description="Epoch for valuation jobs.",
        examples=[3],
    )
    attempt_count: Optional[int] = Field(
        None,
        description="Current retry attempt count for valuation jobs.",
        examples=[1],
    )
    failure_reason: Optional[str] = Field(
        None,
        description="Failure reason (when status=FAILED).",
        examples=["Missing market price for security/date"],
    )


class SupportJobListResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    total: int = Field(..., description="Total jobs matching the filter.", examples=[42])
    skip: int = Field(..., description="Pagination offset.", examples=[0])
    limit: int = Field(..., description="Pagination limit.", examples=[50])
    items: list[SupportJobRecord] = Field(
        ..., description="Operational jobs for support workflows."
    )
