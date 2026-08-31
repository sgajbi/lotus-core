from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.tenant import TenantContext, TenantId

from src.services.event_replay_service.app.application.ingestion_retry_commands import (
    IngestionRetryCommandService,
)
from src.services.event_replay_service.app.application.replay_command_errors import (
    ReplayCommandError,
)
from src.services.ingestion_service.app.DTOs.ingestion_job_dto import IngestionRetryRequest

TENANT_ID = "tenant-a"
TENANT_CONTEXT = TenantContext(TenantId(TENANT_ID))


def _retry_service(
    *,
    ingestion_job_service: MagicMock | None = None,
    replay_payload_dispatcher: MagicMock | None = None,
) -> IngestionRetryCommandService:
    return IngestionRetryCommandService(
        ingestion_job_service=ingestion_job_service or MagicMock(),
        replay_payload_dispatcher=replay_payload_dispatcher or MagicMock(),
    )


@pytest.mark.asyncio
async def test_ingestion_job_retry_dry_run_records_audit_and_returns_job() -> None:
    job = SimpleNamespace(job_id="job-001", status="failed")
    context = SimpleNamespace(
        endpoint="/ingest/transactions",
        request_payload={"transactions": [{"transaction_id": "T1"}]},
        request_payload_policy_version="ingestion-evidence-policy.v1",
        request_payload_representation="source_safe_replay",
        request_payload_replay_eligible=True,
        request_payload_partial_replay_eligible=True,
        request_payload_replay_expires_at=datetime(2099, 8, 16, tzinfo=UTC),
        idempotency_key="idem-001",
        submitted_at=datetime(2026, 7, 4, 9, 0, tzinfo=UTC),
    )
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.assert_retry_allowed_for_records = AsyncMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-001")
    ingestion_job_service.get_job = AsyncMock(return_value=job)
    replay_payload_dispatcher = MagicMock()
    replay_payload_dispatcher.replay_payload = AsyncMock()

    response = await _retry_service(
        ingestion_job_service=ingestion_job_service,
        replay_payload_dispatcher=replay_payload_dispatcher,
    ).retry_ingestion_job(
        tenant_context=TENANT_CONTEXT,
        job_id="job-001",
        retry_request=IngestionRetryRequest(dry_run=True, record_keys=["T1"]),
        requested_by="ops",
    )

    assert response is job
    ingestion_job_service.get_job_replay_context.assert_awaited_once_with(
        "job-001", tenant_id=TENANT_ID
    )
    ingestion_job_service.get_job.assert_awaited_once_with("job-001", tenant_id=TENANT_ID)
    replay_payload_dispatcher.replay_payload.assert_not_awaited()
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()
    _, audit_kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert audit_kwargs["replay_status"] == "dry_run"
    assert audit_kwargs["alternate_lookup_key"] == "job:job-001"


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run", [True, False])
async def test_ingestion_job_retry_rechecks_expiry_after_awaited_controls(
    dry_run: bool,
) -> None:
    context = SimpleNamespace(
        endpoint="/ingest/instruments",
        request_payload={"instruments": [{"security_id": "BOND_1"}]},
        request_payload_policy_version="ingestion-evidence-policy.v1",
        request_payload_representation="source_safe_replay",
        request_payload_replay_eligible=True,
        request_payload_partial_replay_eligible=True,
        request_payload_replay_expires_at=datetime(2099, 8, 16, tzinfo=UTC),
        idempotency_key="idem-001",
        submitted_at=datetime(2026, 7, 4, 9, 0, tzinfo=UTC),
    )

    async def expire_during_retry_permission(*_args, **_kwargs) -> None:
        if dry_run:
            context.request_payload_replay_expires_at = datetime(2000, 1, 1, tzinfo=UTC)

    async def expire_during_duplicate_lookup(*_args, **_kwargs) -> None:
        if not dry_run:
            context.request_payload_replay_expires_at = datetime(2000, 1, 1, tzinfo=UTC)
        return None

    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.assert_retry_allowed_for_records = AsyncMock(
        side_effect=expire_during_retry_permission
    )
    ingestion_job_service.find_successful_replay_audit_by_fingerprint = AsyncMock(
        side_effect=expire_during_duplicate_lookup
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock()
    replay_payload_dispatcher = MagicMock()
    replay_payload_dispatcher.replay_payload = AsyncMock()

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service,
            replay_payload_dispatcher=replay_payload_dispatcher,
        ).retry_ingestion_job(
            tenant_context=TENANT_CONTEXT,
            job_id="job-expired-during-controls",
            retry_request=IngestionRetryRequest(dry_run=dry_run, record_keys=[]),
            requested_by="ops",
        )

    assert exc_info.value.detail["code"] == "INGESTION_JOB_REPLAY_EVIDENCE_EXPIRED"
    replay_payload_dispatcher.replay_payload.assert_not_awaited()
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingestion_job_retry_success_audit_failure_is_not_bookkeeping_success() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions")
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried_and_queued = AsyncMock(return_value=True)
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        side_effect=RuntimeError("audit database unavailable")
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._mark_ingestion_job_retry_replayed(
            tenant_id=TENANT_ID,
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.detail["code"] == "INGESTION_REPLAY_AUDIT_WRITE_FAILED"
    assert exc_info.value.detail["replay_status"] == "replayed"
    assert ingestion_job_service.record_consumer_dlq_replay_audit.await_count == 1


@pytest.mark.asyncio
async def test_ingestion_job_retry_not_found_uses_governed_recovery_detail() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=None)

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._required_job_replay_context("job-missing", tenant_id=TENANT_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "INGESTION_JOB_NOT_FOUND",
        "message": "Ingestion job 'job-missing' was not found.",
        "outcome": "not_found",
        "remediation": "Verify the ingestion job id from the operations job list before retrying.",
        "recovery_path": "ingestion_job_retry",
    }


@pytest.mark.asyncio
async def test_ingestion_job_retry_unsupported_payload_uses_recovery_detail() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(
        return_value=SimpleNamespace(request_payload=None)
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._required_job_replay_context("job-no-payload", tenant_id=TENANT_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INGESTION_JOB_RETRY_UNSUPPORTED"
    assert exc_info.value.detail["outcome"] == "retry_unsupported"
    assert "durable replay payload" in exc_info.value.detail["remediation"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("context_overrides", "expected_failure"),
    [
        ({"request_payload_policy_version": "legacy.v0"}, "policy_unavailable"),
        ({"request_payload_replay_eligible": False}, "policy_ineligible"),
        ({"request_payload_representation": "fingerprint_only"}, "representation_unavailable"),
        ({"request_payload": None}, "payload_unavailable"),
        ({"request_payload_replay_expires_at": None}, "expiry_unavailable"),
    ],
)
async def test_ingestion_job_retry_rejects_unavailable_authority(
    context_overrides: dict[str, object],
    expected_failure: str,
) -> None:
    values = {
        "request_payload_policy_version": "ingestion-evidence-policy.v1",
        "request_payload_replay_eligible": True,
        "request_payload_representation": "source_safe_replay",
        "request_payload": {"instruments": [{"instrument_id": "BOND_1"}]},
        "request_payload_replay_expires_at": datetime(2026, 8, 16, tzinfo=UTC),
    }
    values.update(context_overrides)
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=SimpleNamespace(**values))

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._required_job_replay_context(
            "job-unavailable",
            tenant_id=TENANT_ID,
            observed_at=datetime(2026, 8, 15, tzinfo=UTC),
        )

    assert exc_info.value.detail["code"] == "INGESTION_JOB_RETRY_UNSUPPORTED"
    assert exc_info.value.detail["replay_evidence_failure"] == expected_failure


@pytest.mark.asyncio
async def test_ingestion_job_retry_rejects_expired_authority() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(
        return_value=SimpleNamespace(
            request_payload_policy_version="ingestion-evidence-policy.v1",
            request_payload_replay_eligible=True,
            request_payload_representation="source_safe_replay",
            request_payload={"instruments": [{"instrument_id": "BOND_1"}]},
            request_payload_replay_expires_at=datetime(2026, 8, 14, tzinfo=UTC),
        )
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._required_job_replay_context(
            "job-expired",
            tenant_id=TENANT_ID,
            observed_at=datetime(2026, 8, 15, tzinfo=UTC),
        )

    assert exc_info.value.detail["code"] == "INGESTION_JOB_REPLAY_EVIDENCE_EXPIRED"
    assert exc_info.value.detail["outcome"] == "retry_evidence_expired"
    assert exc_info.value.detail["replay_evidence_failure"] == "expired"


def test_ingestion_job_retry_partial_unsupported_uses_recovery_detail() -> None:
    context = SimpleNamespace(
        endpoint="/ingest/market-prices",
        request_payload={"market_prices": [{"security_id": "S1"}]},
        request_payload_partial_replay_eligible=False,
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        _retry_service()._retry_payload_or_error(
            context=context,
            retry_request=IngestionRetryRequest(record_keys=["S1"]),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INGESTION_PARTIAL_RETRY_UNSUPPORTED"
    assert exc_info.value.detail["outcome"] == "partial_retry_unsupported"
    assert "full stored payload" in exc_info.value.detail["remediation"]


def test_ingestion_job_retry_missing_partial_record_keys_uses_recovery_detail() -> None:
    context = SimpleNamespace(
        endpoint="/ingest/transactions",
        request_payload={"transactions": [{"transaction_id": "T1"}]},
        request_payload_partial_replay_eligible=True,
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        _retry_service()._retry_payload_or_error(
            context=context,
            retry_request=IngestionRetryRequest(record_keys=["T1", "T2"]),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INGESTION_PARTIAL_RETRY_RECORDS_NOT_FOUND"
    assert exc_info.value.detail["outcome"] == "partial_retry_records_not_found"
    assert exc_info.value.detail["missing_record_keys"] == ["T2"]
    assert "stored replay payload" in exc_info.value.detail["remediation"]


@pytest.mark.asyncio
async def test_ingestion_job_retry_blocked_uses_recovery_detail() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.assert_retry_allowed_for_records = AsyncMock(
        side_effect=PermissionError("Retries are blocked while ingestion is paused.")
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._assert_ingestion_retry_allowed(
            submitted_at=datetime(2026, 7, 4, 9, 0),
            replay_record_count=1,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INGESTION_RETRY_BLOCKED"
    assert exc_info.value.detail["outcome"] == "retry_blocked"
    assert "Resume ingestion operations mode" in exc_info.value.detail["remediation"]


@pytest.mark.asyncio
async def test_ingestion_job_retry_duplicate_uses_recovery_detail() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions")
    ingestion_job_service = MagicMock()
    ingestion_job_service.find_successful_replay_audit_by_fingerprint = AsyncMock(
        return_value={"replay_id": "replay-existing", "replay_status": "replayed"}
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-dup")

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._block_duplicate_ingestion_job_retry(
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "INGESTION_RETRY_DUPLICATE_BLOCKED",
        "message": "Retry blocked because an equivalent deterministic replay already succeeded.",
        "outcome": "duplicate_blocked",
        "remediation": (
            "Inspect the existing replay audit before forcing any manual recovery action."
        ),
        "recovery_path": "ingestion_job_retry",
        "replay_fingerprint": "fp-001",
    }
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingestion_job_retry_duplicate_audit_failure_is_governed() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions")
    ingestion_job_service = MagicMock()
    ingestion_job_service.find_successful_replay_audit_by_fingerprint = AsyncMock(
        return_value={"replay_id": "replay-existing", "replay_status": "replayed"}
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        side_effect=RuntimeError("audit database unavailable")
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._block_duplicate_ingestion_job_retry(
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.detail["code"] == "INGESTION_REPLAY_AUDIT_WRITE_FAILED"
    assert exc_info.value.detail["replay_status"] == "duplicate_blocked"


@pytest.mark.asyncio
async def test_ingestion_job_retry_publish_failure_uses_recovery_detail() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions", idempotency_key="idem-001")
    ingestion_job_service = MagicMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-pub")
    ingestion_job_service.mark_failed = AsyncMock(return_value=True)
    replay_payload_dispatcher = MagicMock()
    replay_payload_dispatcher.replay_payload = AsyncMock(
        side_effect=RuntimeError("broker timeout with sensitive downstream detail")
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service,
            replay_payload_dispatcher=replay_payload_dispatcher,
        )._publish_ingestion_job_retry(
            tenant_id=TENANT_ID,
            job_id="job-001",
            context=context,
            retry_request=IngestionRetryRequest(record_keys=["T1"]),
            replay_payload={"transactions": [{"transaction_id": "T1"}]},
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "INGESTION_RETRY_PUBLISH_FAILED",
        "message": (
            "Ingestion job retry could not be published to the downstream ingestion pipeline."
        ),
        "outcome": "publish_failed",
        "remediation": (
            "Check ingestion publisher health and retry after the downstream publish path recovers."
        ),
        "recovery_path": "ingestion_job_retry",
        "replay_audit_id": "audit-pub",
        "replay_fingerprint": "fp-001",
    }
    _, audit_kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert audit_kwargs["replay_reason"] == (
        "Ingestion job retry could not be published to the downstream ingestion pipeline."
    )
    assert "sensitive downstream detail" not in str(audit_kwargs)
    ingestion_job_service.mark_failed.assert_awaited_once()
    mark_failed_positional, mark_failed_args = ingestion_job_service.mark_failed.await_args
    assert mark_failed_positional[1] == audit_kwargs["replay_reason"]
    assert mark_failed_args["failure_phase"] == "retry_publish"
    assert mark_failed_args["failed_record_keys"] == ["T1"]


@pytest.mark.asyncio
async def test_ingestion_job_retry_publish_failure_surfaces_rejected_failure_bookkeeping() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions", idempotency_key="idem-001")
    ingestion_job_service = MagicMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-pub")
    ingestion_job_service.mark_failed = AsyncMock(return_value=False)
    replay_payload_dispatcher = MagicMock()
    replay_payload_dispatcher.replay_payload = AsyncMock(side_effect=RuntimeError("broker timeout"))

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service,
            replay_payload_dispatcher=replay_payload_dispatcher,
        )._publish_ingestion_job_retry(
            tenant_id=TENANT_ID,
            job_id="job-001",
            context=context,
            retry_request=IngestionRetryRequest(record_keys=["T1"]),
            replay_payload={"transactions": [{"transaction_id": "T1"}]},
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INGESTION_RETRY_FAILURE_BOOKKEEPING_REJECTED"
    assert exc_info.value.detail["outcome"] == "bookkeeping_conflict"
    assert exc_info.value.detail["replay_audit_id"] == "audit-pub"
    assert exc_info.value.detail["replay_fingerprint"] == "fp-001"


@pytest.mark.asyncio
async def test_ingestion_job_retry_bookkeeping_failure_uses_recovery_detail() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions")
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried_and_queued = AsyncMock(
        side_effect=RuntimeError("queue state write failed with downstream detail")
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-book")

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._mark_ingestion_job_retry_replayed(
            tenant_id=TENANT_ID,
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "INGESTION_RETRY_BOOKKEEPING_FAILED",
        "message": "Replay publish succeeded but post-publish bookkeeping did not complete.",
        "outcome": "bookkeeping_failed",
        "remediation": (
            "Inspect replay audit state and job queue state before retrying or reconciling "
            "manually."
        ),
        "recovery_path": "ingestion_job_retry",
        "replay_audit_id": "audit-book",
        "replay_fingerprint": "fp-001",
    }
    _, audit_kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert audit_kwargs["replay_reason"] == exc_info.value.detail["message"]
    assert "downstream detail" not in str(audit_kwargs)


@pytest.mark.asyncio
async def test_ingestion_job_retry_bookkeeping_conflict_uses_governed_detail() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions")
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried_and_queued = AsyncMock(return_value=False)
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        return_value="audit-conflict"
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service
        )._mark_ingestion_job_retry_replayed(
            tenant_id=TENANT_ID,
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "INGESTION_RETRY_BOOKKEEPING_CONFLICT",
        "message": (
            "Replay publish succeeded but ingestion job state changed before bookkeeping completed."
        ),
        "outcome": "bookkeeping_conflict",
        "remediation": (
            "Refresh the ingestion job status and replay audit before retrying; another "
            "recovery path changed the job state."
        ),
        "recovery_path": "ingestion_job_retry",
        "replay_audit_id": "audit-conflict",
        "replay_fingerprint": "fp-001",
    }
    ingestion_job_service.mark_retried_and_queued.assert_awaited_once_with(
        "job-001", tenant_id=TENANT_ID
    )
