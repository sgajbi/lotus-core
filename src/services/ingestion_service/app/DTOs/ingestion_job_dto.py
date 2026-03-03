from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

IngestionJobStatus = Literal["accepted", "queued", "failed"]


class IngestionJobResponse(BaseModel):
    job_id: str = Field(
        description="Asynchronous ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    endpoint: str = Field(
        description="Ingestion API endpoint that created this job.",
        examples=["/ingest/transactions"],
    )
    entity_type: str = Field(
        description="Canonical entity type accepted by the endpoint.",
        examples=["transaction"],
    )
    status: IngestionJobStatus = Field(
        description="Current ingestion job lifecycle state.",
        examples=["queued"],
    )
    accepted_count: int = Field(
        ge=0,
        description="Number of records accepted by the ingestion request.",
        examples=[125],
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Client idempotency key if supplied for the request.",
        examples=["ingestion-transactions-batch-20260228-001"],
    )
    correlation_id: str = Field(
        description="Correlation identifier for cross-service traceability.",
        examples=["ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3"],
    )
    request_id: str = Field(
        description="Request identifier for ingress request tracking.",
        examples=["REQ:3a63936e-bf29-41e2-9f16-faf4e561d845"],
    )
    trace_id: str = Field(
        description="Distributed trace identifier for observability stitching.",
        examples=["4bf92f3577b34da6a3ce929d0e0e4736"],
    )
    submitted_at: datetime = Field(
        description="Timestamp when the ingestion job was accepted.",
        examples=["2026-02-28T13:22:24.201Z"],
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when the job reached a terminal or queued state.",
        examples=["2026-02-28T13:22:24.994Z"],
    )
    failure_reason: str | None = Field(
        default=None,
        description="Failure reason when status is failed.",
        examples=["Kafka publish timeout for topic raw_transactions."],
    )
    retry_count: int = Field(
        ge=0,
        description="Number of retry attempts executed for this ingestion job.",
        examples=[1],
    )
    last_retried_at: datetime | None = Field(
        default=None,
        description="Timestamp of the most recent retry attempt.",
        examples=["2026-02-28T13:24:10.512Z"],
    )


class IngestionJobListResponse(BaseModel):
    jobs: list[IngestionJobResponse] = Field(
        description="Ingestion jobs matching the requested filters."
    )
    total: int = Field(
        ge=0,
        description="Number of jobs returned in this response.",
        examples=[20],
    )
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Opaque cursor to fetch the next page of jobs, based on descending ingestion job order."
        ),
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )


class IngestionJobFailureResponse(BaseModel):
    failure_id: str = Field(
        description="Unique failure record identifier for this job failure event.",
        examples=["fail_01J5S27P16BSKQ3R2P2HK67GQZ"],
    )
    job_id: str = Field(
        description="Ingestion job identifier this failure event belongs to.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    failure_phase: str = Field(
        description="Pipeline phase where the job failure occurred.",
        examples=["publish"],
    )
    failure_reason: str = Field(
        description="Detailed failure reason captured at runtime.",
        examples=["Kafka publish timeout for topic raw_transactions."],
    )
    failed_record_keys: list[str] = Field(
        default_factory=list,
        description="Subset of record keys that failed during publish/retry processing.",
        examples=[["TXN-2026-000145", "TXN-2026-000146"]],
    )
    failed_at: datetime = Field(
        description="Timestamp when this failure event was captured.",
        examples=["2026-02-28T13:23:09.021Z"],
    )


class IngestionJobFailureListResponse(BaseModel):
    failures: list[IngestionJobFailureResponse] = Field(
        description="Failure events captured for the requested ingestion job."
    )
    total: int = Field(
        ge=0,
        description="Number of failure events returned in this response.",
        examples=[1],
    )


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


class IngestionBacklogBreakdownItemResponse(BaseModel):
    endpoint: str = Field(
        description="Ingestion endpoint associated with this backlog group.",
        examples=["/ingest/transactions"],
    )
    entity_type: str = Field(
        description="Canonical entity type associated with this backlog group.",
        examples=["transaction"],
    )
    total_jobs: int = Field(
        ge=0,
        description="Total jobs observed for this endpoint/entity group in lookback window.",
        examples=[1250],
    )
    accepted_jobs: int = Field(
        ge=0,
        description="Accepted jobs for this endpoint/entity group.",
        examples=[2],
    )
    queued_jobs: int = Field(
        ge=0,
        description="Queued jobs for this endpoint/entity group.",
        examples=[5],
    )
    failed_jobs: int = Field(
        ge=0,
        description="Failed jobs for this endpoint/entity group.",
        examples=[7],
    )
    backlog_jobs: int = Field(
        ge=0,
        description="Backlog count (accepted + queued) for this endpoint/entity group.",
        examples=[7],
    )
    oldest_backlog_submitted_at: datetime | None = Field(
        default=None,
        description="Submitted timestamp of oldest non-terminal job in this group.",
        examples=["2026-03-01T01:05:12.120Z"],
    )
    oldest_backlog_age_seconds: float = Field(
        ge=0.0,
        description="Age in seconds of oldest non-terminal job in this group.",
        examples=[182.4],
    )
    failure_rate: Decimal = Field(
        ge=Decimal("0"),
        description="Failed jobs divided by total jobs for this group.",
        examples=["0.0056"],
    )


class IngestionBacklogBreakdownResponse(BaseModel):
    lookback_minutes: int = Field(
        ge=1,
        description="Lookback window in minutes used to build backlog breakdown.",
        examples=[1440],
    )
    total_backlog_jobs: int = Field(
        ge=0,
        description="Total backlog jobs across all returned groups.",
        examples=[17],
    )
    groups: list[IngestionBacklogBreakdownItemResponse] = Field(
        description="Backlog and failure-rate breakdown grouped by endpoint and entity_type."
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
        description="Current ingestion operations mode.",
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
        description="Target ingestion operations mode.",
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


class ConsumerDlqEventResponse(BaseModel):
    event_id: str = Field(
        description="Unique audit identifier for a consumer dead-letter event.",
        examples=["cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6"],
    )
    original_topic: str = Field(
        description="Original Kafka topic where message processing failed.",
        examples=["raw_transactions"],
    )
    consumer_group: str = Field(
        description="Consumer group that rejected the message.",
        examples=["persistence-service-group"],
    )
    dlq_topic: str = Field(
        description="Dead-letter topic where failed message was published.",
        examples=["persistence_service.dlq"],
    )
    original_key: str | None = Field(
        default=None,
        description="Original message key, if available.",
        examples=["TXN-2026-000145"],
    )
    error_reason_code: str = Field(
        description="Canonical DLQ reason code for routing, replay policy, and incident analytics.",
        examples=["VALIDATION_ERROR"],
    )
    error_reason: str = Field(
        description="Error reason captured when consumer rejected the message.",
        examples=["ValidationError: portfolio_id is required"],
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation identifier associated with the failed message.",
        examples=["ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3"],
    )
    payload_excerpt: str | None = Field(
        default=None,
        description="Truncated payload excerpt for operational triage.",
        examples=['{"transaction_id":"TXN-2026-000145"}'],
    )
    observed_at: datetime = Field(
        description="Timestamp when the DLQ event was observed.",
        examples=["2026-02-28T22:11:05.812Z"],
    )


class ConsumerDlqEventListResponse(BaseModel):
    events: list[ConsumerDlqEventResponse] = Field(
        description="Consumer dead-letter events for operational triage."
    )
    total: int = Field(
        ge=0,
        description="Number of DLQ events returned.",
        examples=[25],
    )


class IngestionConsumerLagGroupResponse(BaseModel):
    consumer_group: str = Field(
        description="Consumer group observed in dead-letter diagnostics.",
        examples=["persistence-service-group"],
    )
    original_topic: str = Field(
        description="Original topic associated with the lag signal.",
        examples=["raw_transactions"],
    )
    dlq_events: int = Field(
        ge=0,
        description="Number of DLQ events for this consumer/topic in lookback window.",
        examples=[8],
    )
    last_observed_at: datetime | None = Field(
        default=None,
        description="Most recent DLQ observation timestamp for this group/topic.",
        examples=["2026-03-01T08:42:11.019Z"],
    )
    lag_severity: Literal["low", "medium", "high"] = Field(
        description="Derived lag severity from DLQ pressure.",
        examples=["medium"],
    )


class IngestionConsumerLagResponse(BaseModel):
    lookback_minutes: int = Field(
        ge=1,
        description="Lookback window in minutes used to derive consumer lag signals.",
        examples=[60],
    )
    backlog_jobs: int = Field(
        ge=0,
        description="Current non-terminal ingestion jobs (accepted + queued).",
        examples=[11],
    )
    total_groups: int = Field(
        ge=0,
        description="Number of consumer/topic lag groups returned.",
        examples=[3],
    )
    groups: list[IngestionConsumerLagGroupResponse] = Field(
        description="Consumer lag group diagnostics sorted by highest pressure first."
    )


class ConsumerDlqReplayRequest(BaseModel):
    dry_run: bool = Field(
        default=False,
        description="When true, validate replayability and mapping without republishing.",
        examples=[False],
    )


class ConsumerDlqReplayResponse(BaseModel):
    event_id: str = Field(
        description="Consumer DLQ event identifier being replayed.",
        examples=["cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6"],
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation id carried by the failed consumer event.",
        examples=["ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3"],
    )
    job_id: str | None = Field(
        default=None,
        description="Correlated ingestion job replayed from durable payload.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    replay_status: Literal[
        "dry_run",
        "replayed",
        "not_replayable",
        "duplicate_blocked",
    ] = Field(
        description="Replay execution result.",
        examples=["replayed"],
    )
    replay_audit_id: str | None = Field(
        default=None,
        description="Durable replay audit identifier for this replay attempt.",
        examples=["replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P"],
    )
    replay_fingerprint: str | None = Field(
        default=None,
        description="Deterministic fingerprint for this replay mapping and payload.",
        examples=["c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f"],
    )
    message: str = Field(
        description="Human-readable replay outcome for runbook workflows.",
        examples=["Replayed ingestion job from correlated consumer DLQ event."],
    )


class IngestionReplayAuditResponse(BaseModel):
    replay_id: str = Field(
        description="Replay audit identifier.",
        examples=["replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P"],
    )
    recovery_path: Literal["consumer_dlq_replay", "ingestion_job_retry"] = Field(
        description="Recovery path that generated this replay audit event.",
        examples=["consumer_dlq_replay"],
    )
    event_id: str = Field(
        description="Reference event identifier for replay mapping.",
        examples=["cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6"],
    )
    replay_fingerprint: str = Field(
        description="Deterministic fingerprint for replay mapping and payload.",
        examples=["c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f"],
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation id used for replay mapping.",
        examples=["ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3"],
    )
    job_id: str | None = Field(
        default=None,
        description="Associated ingestion job id, when available.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    endpoint: str | None = Field(
        default=None,
        description="Ingestion endpoint used for replay publish.",
        examples=["/ingest/transactions"],
    )
    replay_status: Literal[
        "dry_run", "replayed", "not_replayable", "duplicate_blocked", "failed"
    ] = Field(
        description="Replay outcome status.",
        examples=["replayed"],
    )
    dry_run: bool = Field(
        description="Whether replay request was executed in dry-run mode.",
        examples=[False],
    )
    replay_reason: str = Field(
        description="Human-readable reason or outcome note for this replay event.",
        examples=["Replayed ingestion job from correlated consumer DLQ event."],
    )
    requested_by: str | None = Field(
        default=None,
        description="Ops principal who initiated replay.",
        examples=["ops-token"],
    )
    requested_at: datetime = Field(
        description="Timestamp when replay request was recorded.",
        examples=["2026-03-01T10:12:01.019Z"],
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when replay flow completed.",
        examples=["2026-03-01T10:12:02.039Z"],
    )


class IngestionReplayAuditListResponse(BaseModel):
    audits: list[IngestionReplayAuditResponse] = Field(
        description="Replay audit rows matching requested filters."
    )
    total: int = Field(
        ge=0,
        description="Number of replay audit rows returned.",
        examples=[12],
    )


class IngestionJobRecordStatusResponse(BaseModel):
    job_id: str = Field(
        description="Ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    entity_type: str = Field(
        description="Canonical entity type of the ingestion payload.",
        examples=["transaction"],
    )
    accepted_count: int = Field(
        ge=0,
        description="Number of records accepted by the original ingestion request.",
        examples=[200],
    )
    failed_record_keys: list[str] = Field(
        default_factory=list,
        description="Record keys failed across publish/retry lifecycle.",
        examples=[["TXN-2026-000145", "TXN-2026-000146"]],
    )
    replayable_record_keys: list[str] = Field(
        default_factory=list,
        description="Record keys available for deterministic partial replay operations.",
        examples=[["TXN-2026-000145", "TXN-2026-000146", "TXN-2026-000147"]],
    )


class IngestionIdempotencyDiagnosticItemResponse(BaseModel):
    idempotency_key: str = Field(
        description="Client-supplied idempotency key.",
        examples=["ingestion-transactions-batch-20260301-001"],
    )
    usage_count: int = Field(
        ge=1,
        description="Number of ingestion jobs observed with this idempotency key.",
        examples=[3],
    )
    endpoint_count: int = Field(
        ge=1,
        description="Number of distinct ingestion endpoints using this key.",
        examples=[1],
    )
    endpoints: list[str] = Field(
        description="Distinct ingestion endpoints observed for this idempotency key.",
        examples=[["/ingest/transactions"]],
    )
    first_seen_at: datetime = Field(
        description="First observed timestamp for this idempotency key.",
        examples=["2026-03-01T07:10:11.211Z"],
    )
    last_seen_at: datetime = Field(
        description="Most recent observed timestamp for this idempotency key.",
        examples=["2026-03-01T07:11:01.127Z"],
    )
    collision_detected: bool = Field(
        description="True when same key is reused across multiple endpoints.",
        examples=[False],
    )


class IngestionIdempotencyDiagnosticsResponse(BaseModel):
    lookback_minutes: int = Field(
        ge=1,
        description="Lookback window used for diagnostics.",
        examples=[1440],
    )
    total_keys: int = Field(
        ge=0,
        description="Number of distinct idempotency keys returned.",
        examples=[14],
    )
    collisions: int = Field(
        ge=0,
        description="Number of keys reused across multiple endpoints.",
        examples=[1],
    )
    keys: list[IngestionIdempotencyDiagnosticItemResponse] = Field(
        description="Key-level diagnostics sorted by highest usage count."
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
    breach_failure_rate: bool = Field(
        description="Whether failure rate exceeds threshold.",
        examples=[False],
    )
    breach_backlog_growth: bool = Field(
        description="Whether backlog growth exceeds threshold.",
        examples=[False],
    )
