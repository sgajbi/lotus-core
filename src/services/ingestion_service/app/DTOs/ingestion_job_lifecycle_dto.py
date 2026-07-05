from datetime import datetime
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
        examples=["Kafka publish timeout for topic transactions.raw.received."],
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
        description="Ingestion jobs matching the requested filters and pagination window.",
        examples=[
            [
                {
                    "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
                    "endpoint": "/ingest/transactions",
                    "entity_type": "transaction",
                    "status": "queued",
                    "accepted_count": 125,
                    "correlation_id": "ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3",
                    "request_id": "REQ:3a63936e-bf29-41e2-9f16-faf4e561d845",
                    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                    "submitted_at": "2026-02-28T13:22:24.201Z",
                }
            ]
        ],
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
        examples=["Kafka publish timeout for topic transactions.raw.received."],
    )
    failed_record_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Record keys that failed during publish/retry processing, including batch records "
            "left unpublished after a mid-batch publish failure."
        ),
        examples=[["TXN-2026-000145", "TXN-2026-000146"]],
    )
    failed_at: datetime = Field(
        description="Timestamp when this failure event was captured.",
        examples=["2026-02-28T13:23:09.021Z"],
    )


class IngestionJobFailureListResponse(BaseModel):
    failures: list[IngestionJobFailureResponse] = Field(
        description="Failure events captured for the requested ingestion job.",
        examples=[
            [
                {
                    "failure_id": "fail_01J5S27P16BSKQ3R2P2HK67GQZ",
                    "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
                    "failure_phase": "publish",
                    "failure_reason": "Kafka publish timeout for topic transactions.raw.received.",
                    "failed_record_keys": ["TXN-2026-000145", "TXN-2026-000146"],
                    "failed_at": "2026-02-28T13:23:09.021Z",
                }
            ]
        ],
    )
    total: int = Field(
        ge=0,
        description="Number of failure events returned in this response.",
        examples=[1],
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


class IngestionJobBookkeepingRepairResponse(BaseModel):
    job_id: str = Field(
        description="Ingestion job identifier repaired by the governed bookkeeping command.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    previous_status: IngestionJobStatus = Field(
        description="Job status observed before the repair action.",
        examples=["accepted"],
    )
    repaired_status: IngestionJobStatus = Field(
        description="Job status after the repair action.",
        examples=["queued"],
    )
    recovery_action: str = Field(
        description="Governed operator action that performed the repair.",
        examples=["repair_ingestion_job_bookkeeping"],
    )
    supportability_reason_code: str = Field(
        description="Stable reason code that made the repair action eligible.",
        examples=["POST_PUBLISH_BOOKKEEPING_FAILED"],
    )
    retry_safe: bool = Field(
        description=(
            "False when client retry could duplicate already completed publish or persist work."
        ),
        examples=[False],
    )
    message: str = Field(
        description="Source-safe repair outcome summary.",
        examples=["Ingestion job bookkeeping repaired from accepted to queued."],
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
    payload_fingerprint_count: int = Field(
        ge=0,
        description=(
            "Number of distinct canonical request payload fingerprints observed for this key."
        ),
        examples=[1],
    )
    max_payload_fingerprints_per_endpoint: int = Field(
        ge=0,
        description=(
            "Maximum distinct canonical payload fingerprints observed for any one endpoint "
            "using this key."
        ),
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
        description=(
            "True when the key is reused across multiple endpoints or historical rows show "
            "same-endpoint conflicting payload fingerprints."
        ),
        examples=[False],
    )
    payload_conflict_detected: bool = Field(
        description=(
            "True when historical rows show the same endpoint and idempotency key with more "
            "than one canonical payload fingerprint."
        ),
        examples=[False],
    )
    reuse_classification: str = Field(
        description=(
            "Stable operator classification: conflicting_payload_reuse, cross_endpoint_reuse, "
            "or single_record_or_benign_replay."
        ),
        examples=["single_record_or_benign_replay"],
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
        description="Key-level idempotency diagnostics sorted by highest usage count."
    )
