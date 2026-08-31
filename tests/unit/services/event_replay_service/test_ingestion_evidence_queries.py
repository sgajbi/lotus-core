from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.tenant import TenantContext, TenantId

from src.services.event_replay_service.app.application.ingestion_evidence_queries import (
    IngestionEvidenceQueryService,
)
from src.services.event_replay_service.app.application.ingestion_operations_queries import (
    IngestionOperationsNotFound,
)
from src.services.event_replay_service.app.main import app
from src.services.ingestion_service.app.DTOs.ingestion_job_dto import (
    ConsumerDlqEventResponse,
    IngestionJobFailureResponse,
    IngestionJobResponse,
    IngestionReplayAuditResponse,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import to_job_response
from tests.test_support.tenant import TEST_TENANT_ID

NOW = datetime(2026, 7, 31, 4, 30, tzinfo=UTC)
TENANT_CONTEXT = TenantContext(TenantId("tenant-a"))


def _job(
    *,
    status: str = "queued",
    accepted_count: int = 2,
    retry_count: int = 0,
    request_payload_fingerprint: str | None = "sha256:payload-001",
    idempotency_key: str | None = None,
) -> IngestionJobResponse:
    return IngestionJobResponse(
        job_id="job-001",
        tenant_id=TEST_TENANT_ID,
        endpoint="/ingest/transactions",
        entity_type="transaction",
        status=status,
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
        request_payload_fingerprint=request_payload_fingerprint,
        correlation_id="corr-001",
        request_id="request-001",
        trace_id="trace-001",
        submitted_at=NOW,
        completed_at=NOW,
        retry_count=retry_count,
    )


def _failure(
    *,
    failure_id: str = "failure-001",
    phase: str = "validation",
    keys: list[str] | None = None,
) -> IngestionJobFailureResponse:
    return IngestionJobFailureResponse(
        failure_id=failure_id,
        job_id="job-001",
        failure_phase=phase,
        failure_reason="Source record failed governed validation.",
        failed_record_keys=keys or [],
        failed_at=NOW,
    )


def _dlq(
    *,
    event_id: str = "dlq-001",
    original_key: str = "TXN-001",
    reason_code: str = "VALIDATION_ERROR",
):
    return ConsumerDlqEventResponse(
        event_id=event_id,
        original_topic="transactions.raw.received",
        consumer_group="persistence-service-group",
        dlq_topic="dlq.persistence_service",
        original_key=original_key,
        error_reason_code=reason_code,
        error_reason="Source record failed governed validation.",
        correlation_id="corr-001",
        observed_at=NOW,
    )


def _replay(*, status: str = "replayed") -> IngestionReplayAuditResponse:
    return IngestionReplayAuditResponse(
        replay_id="replay-001",
        recovery_path="consumer_dlq_replay",
        event_id="dlq-001",
        replay_fingerprint="fingerprint-001",
        correlation_id="corr-001",
        job_id="job-001",
        endpoint="/ingest/transactions",
        replay_status=status,
        dry_run=status == "dry_run",
        replay_reason="Governed replay outcome.",
        requested_at=NOW,
        completed_at=NOW,
    )


def _build_bundle(
    *,
    job: IngestionJobResponse,
    failures: list[IngestionJobFailureResponse] | None = None,
    dlq_events: list[ConsumerDlqEventResponse] | None = None,
    replay_audits: list[IngestionReplayAuditResponse] | None = None,
    request_payload=None,
):
    return IngestionEvidenceQueryService(ingestion_job_service=MagicMock())._build_bundle(
        job=job,
        failures=failures or [],
        replay_audits=replay_audits or [],
        consumer_dlq_events=dlq_events or [],
        request_payload=request_payload,
    )


def test_builds_accepted_bundle_with_source_owned_batch_and_validation_profile() -> None:
    bundle = _build_bundle(
        job=_job(),
        request_payload={
            "tenant_id": "tenant-test",
            "validation_profile": "transaction-ingestion",
            "validation_profile_version": "v2",
            "transactions": [
                {
                    "transaction_id": "TXN-002",
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
                {
                    "transaction_id": "TXN-001",
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
            ],
        },
    )

    assert bundle.ingestion_outcome == "accepted"
    assert bundle.validation.accepted_count == 2
    assert bundle.validation.profile_name == "transaction-ingestion"
    assert bundle.validation.profile_version == "v2"
    assert bundle.source_batch_fingerprint is not None
    assert bundle.source_refs[:4] == [
        "source-batch:custody-feed:batch-001",
        "source-record:custody-feed:TXN-001",
        "source-record:custody-feed:TXN-002",
        "source-system:custody-feed",
    ]
    assert bundle.product_version == "v1"
    assert bundle.content_hash.startswith("sha256:")
    assert bundle.snapshot_id == bundle.evidence_bundle_id
    assert bundle.evidence_gate == "ALLOW"
    assert bundle.source_evidence_current is False
    assert bundle.freshness_status == "UNAVAILABLE"
    assert bundle.retention.retention_period_days is None


@pytest.mark.parametrize(
    ("job", "failures", "dlq_events", "expected_outcome", "expected_counts"),
    [
        (_job(status="failed"), [_failure()], [], "rejected", (0, 2, 0)),
        (
            _job(status="failed"),
            [_failure(keys=["TXN-001"])],
            [],
            "partially_accepted",
            (1, 1, 0),
        ),
        (_job(accepted_count=1), [], [_dlq()], "quarantined", (0, 0, 1)),
        (_job(accepted_count=0), [], [], "empty", (0, 0, 0)),
    ],
)
def test_maps_governed_ingestion_outcomes(
    job,
    failures,
    dlq_events,
    expected_outcome,
    expected_counts,
) -> None:
    bundle = _build_bundle(job=job, failures=failures, dlq_events=dlq_events)

    assert bundle.ingestion_outcome == expected_outcome
    assert (
        bundle.validation.accepted_count,
        bundle.validation.rejected_count,
        bundle.validation.quarantined_count,
    ) == expected_counts


def test_replay_success_does_not_overclaim_bookkeeping_repair_completion() -> None:
    bundle = _build_bundle(
        job=_job(retry_count=1),
        failures=[_failure(phase="queue_bookkeeping")],
        replay_audits=[_replay()],
    )

    assert bundle.ingestion_outcome == "accepted"
    assert bundle.replay_posture == "replayed"
    assert bundle.repair_posture == "unknown"
    assert "BOOKKEEPING_REPAIR_UNPROVEN" in bundle.evidence_gate_reasons


def test_queued_status_alone_does_not_overclaim_bookkeeping_repair() -> None:
    bundle = _build_bundle(
        job=_job(retry_count=0),
        failures=[_failure(phase="queue_bookkeeping")],
    )

    assert bundle.repair_posture == "unknown"
    assert bundle.evidence_gate == "REVIEW_REQUIRED"
    assert "BOOKKEEPING_REPAIR_UNPROVEN" in bundle.evidence_gate_reasons


def test_processing_dlq_is_not_misclassified_as_quarantine_and_blocks_gate() -> None:
    bundle = _build_bundle(
        job=_job(accepted_count=1),
        dlq_events=[_dlq(reason_code="PERSISTENCE_TIMEOUT")],
    )

    assert bundle.ingestion_outcome == "accepted"
    assert bundle.validation.quarantined_count == 0
    assert bundle.evidence_gate == "BLOCK"
    assert "CORRELATED_PROCESSING_FAILURE" in bundle.evidence_gate_reasons


def test_successfully_replayed_processing_dlq_no_longer_blocks_gate() -> None:
    bundle = _build_bundle(
        job=_job(),
        dlq_events=[_dlq(reason_code="PERSISTENCE_TIMEOUT")],
        replay_audits=[_replay()],
    )

    assert bundle.replay_posture == "replayed"
    assert bundle.evidence_gate == "ALLOW"
    assert "CORRELATED_PROCESSING_FAILURE" not in bundle.evidence_gate_reasons


def test_truncated_evidence_is_explicit_and_cannot_pass_gate() -> None:
    bundle = IngestionEvidenceQueryService(ingestion_job_service=MagicMock())._build_bundle(
        job=_job(),
        failures=[],
        replay_audits=[],
        consumer_dlq_events=[],
        request_payload=None,
        evidence_complete=False,
    )

    assert bundle.evidence_complete is False
    assert bundle.evidence_limit == 500
    assert bundle.data_quality_status == "UNKNOWN"
    assert bundle.evidence_gate == "REVIEW_REQUIRED"
    assert bundle.evidence_gate_reasons == ["EVIDENCE_LIMIT_EXCEEDED"]


def test_non_terminal_accepted_job_requires_review() -> None:
    bundle = _build_bundle(job=_job(status="accepted"))

    assert bundle.ingestion_outcome == "accepted"
    assert bundle.evidence_gate == "REVIEW_REQUIRED"
    assert bundle.evidence_gate_reasons == ["INGESTION_JOB_PENDING"]


def test_bundle_identity_changes_with_persisted_request_fingerprint() -> None:
    first = _build_bundle(job=_job(request_payload_fingerprint="sha256:first"))
    second = _build_bundle(job=_job(request_payload_fingerprint="sha256:second"))

    assert first.evidence_bundle_id != second.evidence_bundle_id


@pytest.mark.parametrize(
    ("raw_key", "include_raw_key", "expected_raw_key", "expects_reference"),
    [
        ("caller-key", True, "caller-key", True),
        ("caller-key", False, None, True),
        (None, False, None, False),
    ],
)
def test_canonical_job_mapping_applies_idempotency_disclosure_posture(
    raw_key: str | None,
    include_raw_key: bool,
    expected_raw_key: str | None,
    expects_reference: bool,
) -> None:
    persisted = _job(
        request_payload_fingerprint="sha256:persisted",
        idempotency_key=raw_key,
    ).model_dump()
    row = SimpleNamespace(
        **persisted,
        request_payload={},
    )

    response = to_job_response(
        row,
        reference_key_id="ops-test",
        reference_hmac_secret="unit-test-idempotency-reference-secret",
        include_raw_idempotency_key=include_raw_key,
    )

    assert response.request_payload_fingerprint == "sha256:persisted"
    assert response.model_dump()["idempotency_key"] == expected_raw_key
    assert (response.idempotency_key_reference is not None) is expects_reference
    if response.idempotency_key_reference is not None:
        assert response.idempotency_key_reference.startswith("hmac-sha256:v1:ops-test:")


def test_ambiguous_source_scope_remains_null_instead_of_using_request_hash() -> None:
    bundle = _build_bundle(
        job=_job(),
        request_payload={
            "transactions": [
                {
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-001",
                },
                {
                    "source_system": "custody-feed",
                    "source_batch_id": "batch-002",
                },
            ]
        },
    )

    assert bundle.source_system is None
    assert bundle.source_batch_id is None
    assert bundle.source_batch_fingerprint is None
    assert not any(reference.startswith("source-batch:") for reference in bundle.source_refs)


@pytest.mark.asyncio
async def test_get_bundle_correlates_existing_stores_without_parallel_persistence() -> None:
    job = _job()
    failure = _failure(keys=["TXN-001"])
    dlq_event = _dlq()
    replay = _replay()
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(return_value=job)
    ingestion_job_service.list_failures = AsyncMock(return_value=[failure])
    ingestion_job_service.list_replay_audits = AsyncMock(return_value=[replay])
    ingestion_job_service.list_consumer_dlq_events_by_job_id = AsyncMock(return_value=[dlq_event])
    ingestion_job_service.list_consumer_dlq_events_by_event_ids = AsyncMock(
        return_value=[dlq_event]
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(
        return_value=SimpleNamespace(request_payload=None)
    )

    bundle = await IngestionEvidenceQueryService(
        ingestion_job_service=ingestion_job_service
    ).get_evidence_bundle("job-001", tenant_context=TENANT_CONTEXT)

    assert bundle.job == job
    assert bundle.failures == [failure]
    assert bundle.consumer_dlq_events == [dlq_event]
    assert bundle.replay_audits == [replay]
    ingestion_job_service.get_job.assert_awaited_once_with("job-001", tenant_id="tenant-a")
    ingestion_job_service.get_job_replay_context.assert_awaited_once_with(
        "job-001", tenant_id="tenant-a"
    )
    ingestion_job_service.list_consumer_dlq_events_by_job_id.assert_awaited_once_with(
        "job-001",
        limit=501,
    )
    ingestion_job_service.list_replay_audits.assert_awaited_once_with(
        tenant_id="tenant-a",
        job_id="job-001",
        limit=501,
        recovery_path=None,
        replay_status=None,
        replay_fingerprint=None,
    )
    ingestion_job_service.list_consumer_dlq_events_by_event_ids.assert_awaited_once_with(
        ("dlq-001",),
        limit=501,
    )


@pytest.mark.asyncio
async def test_get_bundle_links_dlq_by_replay_event_when_message_correlation_was_absent() -> None:
    job = _job()
    dlq_event = _dlq()
    replay = _replay()
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(return_value=job)
    ingestion_job_service.list_failures = AsyncMock(return_value=[])
    ingestion_job_service.list_replay_audits = AsyncMock(return_value=[replay])
    ingestion_job_service.list_consumer_dlq_events_by_job_id = AsyncMock(return_value=[])
    ingestion_job_service.list_consumer_dlq_events_by_event_ids = AsyncMock(
        return_value=[dlq_event]
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=None)

    bundle = await IngestionEvidenceQueryService(
        ingestion_job_service=ingestion_job_service
    ).get_evidence_bundle("job-001", tenant_context=TENANT_CONTEXT)

    assert bundle.consumer_dlq_events == [dlq_event]
    assert "consumer-dlq:dlq-001" in bundle.evidence_references


@pytest.mark.asyncio
async def test_get_bundle_rejects_replay_event_owned_by_another_job() -> None:
    job = _job()
    foreign_dlq_event = _dlq().model_copy(update={"ingestion_job_id": "job-002"})
    replay = _replay()
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(return_value=job)
    ingestion_job_service.list_failures = AsyncMock(return_value=[])
    ingestion_job_service.list_replay_audits = AsyncMock(return_value=[replay])
    ingestion_job_service.list_consumer_dlq_events_by_job_id = AsyncMock(return_value=[])
    ingestion_job_service.list_consumer_dlq_events_by_event_ids = AsyncMock(
        return_value=[foreign_dlq_event]
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=None)

    bundle = await IngestionEvidenceQueryService(
        ingestion_job_service=ingestion_job_service
    ).get_evidence_bundle("job-001", tenant_context=TENANT_CONTEXT)

    assert bundle.consumer_dlq_events == []
    assert "consumer-dlq:dlq-001" not in bundle.evidence_references


@pytest.mark.asyncio
async def test_get_bundle_rejects_unknown_job_before_fetching_related_evidence() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(return_value=None)

    with pytest.raises(IngestionOperationsNotFound) as exc_info:
        await IngestionEvidenceQueryService(
            ingestion_job_service=ingestion_job_service
        ).get_evidence_bundle("missing-job", tenant_context=TENANT_CONTEXT)

    assert exc_info.value.code == "INGESTION_JOB_NOT_FOUND"
    ingestion_job_service.get_job.assert_awaited_once_with("missing-job", tenant_id="tenant-a")
    ingestion_job_service.list_failures.assert_not_called()


def test_openapi_exposes_stable_ingestion_evidence_bundle_contract() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/ingestion/jobs/{job_id}/evidence"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    example = operation["responses"]["200"]["content"]["application/json"]["example"]
    bundle_schema = schema["components"]["schemas"]["IngestionEvidenceBundleResponse"]

    assert operation["summary"] == "Get governed ingestion evidence bundle"
    assert operation["x-lotus-source-data-product"]["product_name"] == ("IngestionEvidenceBundle")
    assert response_schema["$ref"].endswith("/IngestionEvidenceBundleResponse")
    assert {
        "evidence_bundle_id",
        "product_version",
        "ingestion_outcome",
        "replay_posture",
        "repair_posture",
        "source_batch_fingerprint",
        "evidence_complete",
        "evidence_gate",
        "validation",
        "retention",
        "job",
        "failures",
        "consumer_dlq_events",
        "replay_audits",
    }.issubset(bundle_schema["properties"])
    assert example["product_name"] == "IngestionEvidenceBundle"
    assert "retention_period_days" not in example["retention"]
