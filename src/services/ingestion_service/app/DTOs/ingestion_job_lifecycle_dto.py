from datetime import datetime
from typing import Any, Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, Field

from .ingestion_job_replay_dto import ConsumerDlqEventResponse, IngestionReplayAuditResponse

IngestionJobStatus = Literal["accepted", "queued", "failed"]
IngestionOutcome = Literal[
    "accepted",
    "partially_accepted",
    "rejected",
    "quarantined",
    "empty",
]
IngestionReplayPosture = Literal[
    "not_requested",
    "dry_run_only",
    "replayed",
    "replay_failed",
    "replay_bookkeeping_failed",
]
IngestionRepairPosture = Literal["not_required", "required", "repaired", "unknown"]
IngestionPayloadClassification = Literal[
    "internal", "confidential", "restricted", "legacy_unclassified"
]
IngestionPayloadRepresentation = Literal[
    "source_safe_replay", "fingerprint_only", "legacy_redacted"
]


class IngestionJobResponse(BaseModel):
    job_id: str = Field(
        description="Asynchronous ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    tenant_id: str = Field(
        description="Source-owned tenant authority admitted for this ingestion job.",
        examples=["tenant-sg"],
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
        deprecated=True,
        description=(
            "Deprecated raw-key field. It may be echoed to the originating ingestion request "
            "but is always null in operational job list, detail, retry, and evidence projections."
        ),
    )
    idempotency_key_reference: str | None = Field(
        default=None,
        description=(
            "Key-versioned HMAC-SHA-256 pseudonymous reference for the client idempotency key; "
            "null when no key was supplied. Rotation of the declared key id intentionally "
            "changes the value."
        ),
        examples=[
            "hmac-sha256:v1:ops-2026-08:"
            "6a144175d216004612747a27a1daecc816334b295076941e203816799b4b1b67"
        ],
    )
    request_payload_fingerprint: str | None = Field(
        default=None,
        description=(
            "Deterministic, key-versioned HMAC-SHA-256 fingerprint of the complete original "
            "request payload. It supports equality checks without enabling offline confirmation "
            "of guessable restricted values."
        ),
        examples=[
            "hmac-sha256:v1:ops-2026-08:c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f"
        ],
    )
    request_payload_policy_version: str | None = Field(
        default=None,
        description="Version of the durable payload evidence policy applied at ingestion time.",
        examples=["ingestion-evidence-policy.v1"],
    )
    request_payload_classification: IngestionPayloadClassification | None = Field(
        default=None,
        description="Governed information classification of the submitted payload family.",
        examples=["restricted"],
    )
    request_payload_representation: IngestionPayloadRepresentation | None = Field(
        default=None,
        description=(
            "Durable representation retained for the request: bounded source-safe replay, "
            "fingerprint only, or a non-authoritative legacy redaction."
        ),
        examples=["fingerprint_only"],
    )
    request_payload_replay_eligible: bool | None = Field(
        default=None,
        description="Whether the policy snapshot authorizes full payload replay.",
        examples=[False],
    )
    request_payload_partial_replay_eligible: bool | None = Field(
        default=None,
        description="Whether the policy snapshot authorizes record-filtered replay.",
        examples=[False],
    )
    request_payload_replay_expires_at: datetime | None = Field(
        default=None,
        description=(
            "Technical expiry of replay authority; null for fingerprint-only or legacy evidence."
        ),
        examples=["2026-08-15T13:22:24.201Z"],
    )
    request_payload_retention_authority: str | None = Field(
        default=None,
        description="Durable issue or policy authority governing retention and deletion posture.",
        examples=["lotus-core#708"],
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
    failure_status_code: int | None = Field(
        default=None,
        ge=400,
        le=599,
        description=("Original HTTP failure status preserved for deterministic idempotent replay."),
        examples=[409],
    )
    failure_code: str | None = Field(
        default=None,
        description="Stable original error code preserved for deterministic idempotent replay.",
        examples=["MARKET_PRICE_SOURCE_FACT_CONFLICT"],
    )
    failure_detail: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Source-safe original error detail preserved for deterministic idempotent replay; "
            "raw request payloads and secrets are excluded."
        ),
        examples=[
            {
                "message": "The authoritative source version conflicts with retained history.",
                "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
            }
        ],
    )
    failure_headers: dict[str, str] | None = Field(
        default=None,
        description="Safe response headers that must be reproduced with a failed replay.",
        examples=[{"Retry-After": "30"}],
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


class IngestionEvidenceValidationSummary(BaseModel):
    profile_name: str | None = Field(
        default=None,
        description=(
            "Source-declared validation profile, when one unambiguous value is retained "
            "in the ingestion payload."
        ),
        examples=["transaction-ingestion"],
    )
    profile_version: str | None = Field(
        default=None,
        description=(
            "Source-declared validation profile or schema version, when retained in the "
            "ingestion payload."
        ),
        examples=["v1"],
    )
    received_count: int = Field(
        ge=0,
        description="Number of records represented by the retained ingestion evidence.",
        examples=[125],
    )
    accepted_count: int = Field(
        ge=0,
        description="Records without durable rejection or quarantine evidence.",
        examples=[123],
    )
    rejected_count: int = Field(
        ge=0,
        description="Records with durable ingestion failure evidence outside quarantine.",
        examples=[1],
    )
    quarantined_count: int = Field(
        ge=0,
        description="Records represented by correlated consumer dead-letter evidence.",
        examples=[1],
    )
    finding_count: int = Field(
        ge=0,
        description="Number of durable validation findings referenced by this bundle.",
        examples=[2],
    )
    finding_references: list[str] = Field(
        default_factory=list,
        description=(
            "Stable failure or consumer-DLQ references carrying validation findings; "
            "details remain in the embedded canonical DTOs."
        ),
        examples=[["ingestion-failure:fail_01J5S27", "consumer-dlq:cdlq_01J5VK4"]],
    )


class IngestionEvidenceRetentionPosture(BaseModel):
    retention_class: str = Field(
        description="Governed evidence-retention classification selected by runtime policy.",
        examples=["governed_operational_evidence"],
    )
    archival_posture: str = Field(
        description="Governed archival classification selected by runtime policy.",
        examples=["policy_managed"],
    )
    retention_period_days: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Authoritative retention duration when configured; null means this service "
            "has no legal or records-management duration authority."
        ),
        examples=[2555],
    )


class IngestionEvidenceBundleResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["IngestionEvidenceBundle"] = product_name_field("IngestionEvidenceBundle")
    product_version: Literal["v1"] = product_version_field()
    evidence_bundle_id: str = Field(
        description="Deterministic identifier for the exact durable evidence composition.",
        examples=["ingev_8e68038a37f50d0e3f693f1e2081b718"],
    )
    ingestion_outcome: IngestionOutcome = Field(
        description="Governed source-batch ingestion outcome classification.",
        examples=["partially_accepted"],
    )
    replay_posture: IngestionReplayPosture = Field(
        description="Current replay posture derived from durable replay audit rows.",
        examples=["replayed"],
    )
    repair_posture: IngestionRepairPosture = Field(
        description="Current bookkeeping-repair posture derived from job and failure evidence.",
        examples=["repaired"],
    )
    source_system: str | None = Field(
        default=None,
        description="Unambiguous source-owned system retained in the request payload.",
        examples=["custody-feed"],
    )
    source_batch_id: str | None = Field(
        default=None,
        description="Unambiguous source-owned batch identifier retained in the request payload.",
        examples=["custody-20260731-001"],
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description=(
            "Stable job, failure, consumer-DLQ, and replay-audit references included in "
            "this bundle."
        ),
    )
    evidence_complete: bool = Field(
        description=(
            "True when all correlated failure, replay, and consumer-DLQ rows fit within "
            "the governed response evidence limit."
        ),
        examples=[True],
    )
    evidence_limit: int = Field(
        ge=1,
        description="Maximum rows retained per correlated evidence family in this response.",
        examples=[500],
    )
    evidence_gate: Literal["ALLOW", "BLOCK", "REVIEW_REQUIRED"] = Field(
        description=(
            "Fail-closed consumer posture derived from outcome, recovery, and completeness."
        ),
        examples=["BLOCK"],
    )
    evidence_gate_reasons: list[str] = Field(
        default_factory=list,
        description="Bounded reasons for a blocked or review-required evidence posture.",
        examples=[["PARTIALLY_ACCEPTED_SOURCE_BATCH"]],
    )
    validation: IngestionEvidenceValidationSummary = Field(
        description="Validation counts, findings, and source-declared profile evidence."
    )
    retention: IngestionEvidenceRetentionPosture = Field(
        description="Governed retention and archival classification without inferred legal terms."
    )
    job: IngestionJobResponse = Field(description="Canonical ingestion job lifecycle evidence.")
    failures: list[IngestionJobFailureResponse] = Field(
        default_factory=list,
        description="Canonical ingestion job failure evidence.",
    )
    consumer_dlq_events: list[ConsumerDlqEventResponse] = Field(
        default_factory=list,
        description="Consumer dead-letter evidence correlated to the ingestion job.",
    )
    replay_audits: list[IngestionReplayAuditResponse] = Field(
        default_factory=list,
        description="Replay audit evidence associated with the ingestion job.",
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
    idempotency_key: None = Field(
        default=None,
        deprecated=True,
        description=(
            "Deprecated raw-key field. Always null because operator diagnostics do not disclose "
            "caller-supplied idempotency keys."
        ),
    )
    idempotency_key_reference: str = Field(
        description=(
            "Stable, key-versioned HMAC-SHA-256 pseudonymous reference for the client "
            "idempotency key. Rotation of the declared key id intentionally changes the value."
        ),
        examples=[
            "hmac-sha256:v1:ops-2026-08:"
            "6a144175d216004612747a27a1daecc816334b295076941e203816799b4b1b67"
        ],
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
