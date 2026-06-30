from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConsumerDlqEventResponse(BaseModel):
    event_id: str = Field(
        description="Unique audit identifier for a consumer dead-letter event.",
        examples=["cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6"],
    )
    original_topic: str = Field(
        description="Original Kafka topic where message processing failed.",
        examples=["transactions.raw.received"],
    )
    consumer_group: str = Field(
        description="Consumer group that rejected the message.",
        examples=["persistence-service-group"],
    )
    dlq_topic: str = Field(
        description="Dead-letter topic where failed message was published.",
        examples=["dlq.persistence_service"],
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
        description="Redacted, truncated payload excerpt for operational triage.",
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
        examples=["transactions.raw.received"],
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
        description=(
            "When true, validate replayability and replay mapping without republishing messages."
        ),
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
        "dry_run",
        "replayed",
        "replayed_bookkeeping_failed",
        "not_replayable",
        "duplicate_blocked",
        "failed",
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
        description="Replay audit rows matching the requested filters and time window."
    )
    total: int = Field(
        ge=0,
        description="Number of replay audit rows returned.",
        examples=[12],
    )
