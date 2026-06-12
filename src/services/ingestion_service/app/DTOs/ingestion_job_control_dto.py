from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IngestionJobStatus = Literal["accepted", "queued", "failed"]


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
