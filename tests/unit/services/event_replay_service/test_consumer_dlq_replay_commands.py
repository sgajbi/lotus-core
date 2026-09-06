from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.tenant import TenantContext, TenantId

from src.services.event_replay_service.app.application.consumer_dlq_replay_commands import (
    ConsumerDlqReplayCommand,
    ConsumerDlqReplayCommandService,
    ConsumerDlqReplayResult,
)
from src.services.event_replay_service.app.application.replay_command_errors import (
    ReplayCommandError,
)

TENANT_ID = "tenant-a"
TENANT_CONTEXT = TenantContext(TenantId(TENANT_ID))


def _consumer_service(
    *,
    ingestion_job_service: MagicMock | None = None,
    replay_payload_dispatcher: MagicMock | None = None,
) -> ConsumerDlqReplayCommandService:
    return ConsumerDlqReplayCommandService(
        ingestion_job_service=ingestion_job_service or MagicMock(),
        replay_payload_dispatcher=replay_payload_dispatcher or MagicMock(),
    )


def _replay_context(**overrides: object) -> SimpleNamespace:
    values = {
        "tenant_id": TENANT_ID,
        "endpoint": "/ingest/instruments",
        "request_payload": {"instruments": [{"instrument_id": "BOND_1"}]},
        "request_payload_policy_version": "ingestion-evidence-policy.v1",
        "request_payload_representation": "source_safe_replay",
        "request_payload_replay_eligible": True,
        "request_payload_replay_expires_at": datetime(2099, 8, 14, tzinfo=UTC),
        "idempotency_key": "idem-001",
        "submitted_at": datetime(2026, 7, 4, 9, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_consumer_dlq_replay_dry_run_records_audit_without_publish() -> None:
    context = _replay_context()
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_consumer_dlq_event = AsyncMock(
        return_value=SimpleNamespace(event_id="dlq-001", correlation_id="corr-001")
    )
    ingestion_job_service.get_unique_replayable_job_by_correlation_id = AsyncMock(
        return_value=SimpleNamespace(job_id="job-001", correlation_id="corr-001", status="queued")
    )
    ingestion_job_service.list_jobs = AsyncMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.find_successful_replay_audit_by_fingerprint = AsyncMock(return_value=None)
    ingestion_job_service.assert_retry_allowed_for_records = AsyncMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-001")
    replay_payload_dispatcher = MagicMock()
    replay_payload_dispatcher.replay_payload = AsyncMock()

    response = await _consumer_service(
        ingestion_job_service=ingestion_job_service,
        replay_payload_dispatcher=replay_payload_dispatcher,
    ).replay_consumer_dlq_event(
        event_id="dlq-001",
        command=ConsumerDlqReplayCommand(
            tenant_context=TENANT_CONTEXT, dry_run=True, requested_by="ops"
        ),
    )

    assert response.replay_status == "dry_run"
    assert response.job_id == "job-001"
    assert response.replay_audit_id == "audit-001"
    ingestion_job_service.get_unique_replayable_job_by_correlation_id.assert_awaited_once_with(
        "corr-001", tenant_id=TENANT_ID
    )
    ingestion_job_service.list_jobs.assert_not_awaited()
    replay_payload_dispatcher.replay_payload.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run", [True, False])
async def test_consumer_dlq_replay_rechecks_expiry_after_awaited_controls(
    dry_run: bool,
) -> None:
    context = _replay_context()

    async def expire_during_retry_permission(*_args, **_kwargs) -> None:
        if dry_run:
            context.request_payload_replay_expires_at = datetime(2000, 1, 1, tzinfo=UTC)

    async def expire_during_duplicate_lookup(*_args, **_kwargs) -> None:
        if not dry_run:
            context.request_payload_replay_expires_at = datetime(2000, 1, 1, tzinfo=UTC)
        return None

    ingestion_job_service = MagicMock()
    ingestion_job_service.get_consumer_dlq_event = AsyncMock(
        return_value=SimpleNamespace(event_id="dlq-001", correlation_id="corr-001")
    )
    ingestion_job_service.get_unique_replayable_job_by_correlation_id = AsyncMock(
        return_value=SimpleNamespace(job_id="job-001", correlation_id="corr-001", status="queued")
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.find_successful_replay_audit_by_fingerprint = AsyncMock(
        side_effect=expire_during_duplicate_lookup
    )
    ingestion_job_service.assert_retry_allowed_for_records = AsyncMock(
        side_effect=expire_during_retry_permission
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-001")
    replay_payload_dispatcher = MagicMock()
    replay_payload_dispatcher.replay_payload = AsyncMock()

    response = await _consumer_service(
        ingestion_job_service=ingestion_job_service,
        replay_payload_dispatcher=replay_payload_dispatcher,
    ).replay_consumer_dlq_event(
        event_id="dlq-001",
        command=ConsumerDlqReplayCommand(
            tenant_context=TENANT_CONTEXT, dry_run=dry_run, requested_by="ops"
        ),
    )

    assert response.replay_status == "not_replayable"
    assert response.message.endswith("expired.")
    replay_payload_dispatcher.replay_payload.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumer_dlq_replay_uses_durable_owner_without_correlation_lookup() -> None:
    context = _replay_context()
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_consumer_dlq_event = AsyncMock(
        return_value=SimpleNamespace(
            event_id="dlq-001",
            correlation_id=None,
            ingestion_job_id="job-001",
        )
    )
    ingestion_job_service.get_job = AsyncMock(
        return_value=SimpleNamespace(job_id="job-001", status="queued")
    )
    ingestion_job_service.get_unique_replayable_job_by_correlation_id = AsyncMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.find_successful_replay_audit_by_fingerprint = AsyncMock(return_value=None)
    ingestion_job_service.assert_retry_allowed_for_records = AsyncMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-001")

    response = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    ).replay_consumer_dlq_event(
        event_id="dlq-001",
        command=ConsumerDlqReplayCommand(
            tenant_context=TENANT_CONTEXT, dry_run=True, requested_by="ops"
        ),
    )

    assert response.job_id == "job-001"
    assert response.replay_status == "dry_run"
    ingestion_job_service.get_job.assert_awaited_once_with("job-001", tenant_id=TENANT_ID)
    ingestion_job_service.get_unique_replayable_job_by_correlation_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumer_dlq_mandatory_replay_audit_returns_replay_id() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-123")

    replay_id = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    )._record_mandatory_replay_audit(
        event_id="dlq-123",
        replay_fingerprint="fp-456",
        correlation_id="corr-123",
        job_id="job-123",
        endpoint="/ingest/transactions",
        replay_status="dry_run",
        dry_run=True,
        replay_reason="dry-run",
        requested_by="ops",
        correlation_missing_reason="message_correlation_id_absent",
        alternate_lookup_key="consumer_dlq|topic=transactions.raw.received|event=dlq-123",
    )

    assert replay_id == "audit-123"
    _, kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert kwargs["recovery_path"] == "consumer_dlq_replay"
    assert kwargs["correlation_missing_reason"] == "message_correlation_id_absent"
    assert (
        kwargs["alternate_lookup_key"]
        == "consumer_dlq|topic=transactions.raw.received|event=dlq-123"
    )


@pytest.mark.asyncio
async def test_consumer_dlq_mandatory_replay_audit_failure_raises_governed_error() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _consumer_service(
            ingestion_job_service=ingestion_job_service
        )._record_mandatory_replay_audit(
            event_id="dlq-123",
            replay_fingerprint="fp-456",
            correlation_id="corr-123",
            job_id="job-123",
            endpoint="/ingest/transactions",
            replay_status="replayed",
            dry_run=False,
            replay_reason="replayed",
            requested_by="ops",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "INGESTION_REPLAY_AUDIT_WRITE_FAILED",
        "message": "Replay audit could not be recorded; replay outcome was not acknowledged.",
        "recovery_path": "consumer_dlq_replay",
        "event_id": "dlq-123",
        "job_id": "job-123",
        "replay_status": "replayed",
        "replay_fingerprint": "fp-456",
    }


@pytest.mark.asyncio
async def test_consumer_dlq_replay_candidate_records_no_correlated_job_response() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_unique_replayable_job_by_correlation_id = AsyncMock(return_value=None)
    ingestion_job_service.list_jobs = AsyncMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-001")

    response = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    )._consumer_dlq_replay_candidate_or_result(
        event_id="dlq-001",
        correlation_id="corr-001",
        tenant_id=TENANT_ID,
        dry_run=True,
        requested_by="ops",
    )

    assert response.replay_status == "not_replayable"
    assert response.job_id is None
    assert response.message == "No correlated ingestion job found for consumer DLQ event."
    ingestion_job_service.get_unique_replayable_job_by_correlation_id.assert_awaited_once_with(
        "corr-001", tenant_id=TENANT_ID
    )
    ingestion_job_service.list_jobs.assert_not_awaited()
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_dlq_not_replayable_records_missing_correlation_diagnostics() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-003")

    response = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    )._consumer_dlq_not_replayable_result(
        event_id="dlq-003",
        correlation_id=None,
        correlation_missing_reason="message_correlation_id_absent",
        alternate_lookup_key="consumer_dlq|topic=transactions.raw.received|event=dlq-003",
        job_id=None,
        endpoint=None,
        dry_run=True,
        replay_reason="DLQ event has no correlation id.",
        requested_by="ops",
    )

    assert response.replay_status == "not_replayable"
    assert response.correlation_missing_reason == "message_correlation_id_absent"
    assert (
        response.alternate_lookup_key
        == "consumer_dlq|topic=transactions.raw.received|event=dlq-003"
    )
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()
    _, kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert kwargs["correlation_missing_reason"] == "message_correlation_id_absent"
    assert kwargs["alternate_lookup_key"] == (
        "consumer_dlq|topic=transactions.raw.received|event=dlq-003"
    )


@pytest.mark.asyncio
async def test_consumer_dlq_replay_candidate_records_missing_payload_response() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_unique_replayable_job_by_correlation_id = AsyncMock(
        return_value={"job_id": "job-001", "correlation_id": "corr-001", "status": "failed"}
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(
        return_value=_replay_context(request_payload=None)
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-002")

    response = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    )._consumer_dlq_replay_candidate_or_result(
        event_id="dlq-001",
        correlation_id="corr-001",
        tenant_id=TENANT_ID,
        dry_run=False,
        requested_by="ops",
    )

    assert response.replay_status == "not_replayable"
    assert response.job_id == "job-001"
    assert response.message.endswith("payload_unavailable.")
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_dlq_replay_candidate_returns_replayable_context() -> None:
    context = _replay_context()
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_unique_replayable_job_by_correlation_id = AsyncMock(
        return_value=SimpleNamespace(job_id="job-001", correlation_id="corr-001", status="queued")
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock()

    candidate = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    )._consumer_dlq_replay_candidate_or_result(
        event_id="dlq-001",
        correlation_id="corr-001",
        tenant_id=TENANT_ID,
        dry_run=False,
        requested_by="ops",
    )

    assert not isinstance(candidate, ConsumerDlqReplayResult)
    assert candidate.job_id == "job-001"
    assert candidate.context is context
    assert len(candidate.replay_fingerprint) == 64
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumer_dlq_replay_fingerprint_is_scoped_to_event() -> None:
    context = _replay_context()
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_unique_replayable_job_by_correlation_id = AsyncMock(
        return_value=SimpleNamespace(job_id="job-001", correlation_id="corr-001", status="failed")
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock()
    service = _consumer_service(ingestion_job_service=ingestion_job_service)

    first = await service._consumer_dlq_replay_candidate_or_result(
        event_id="dlq-001",
        correlation_id="corr-001",
        tenant_id=TENANT_ID,
        dry_run=False,
        requested_by="ops",
    )
    second = await service._consumer_dlq_replay_candidate_or_result(
        event_id="dlq-002",
        correlation_id="corr-001",
        tenant_id=TENANT_ID,
        dry_run=False,
        requested_by="ops",
    )

    assert not isinstance(first, ConsumerDlqReplayResult)
    assert not isinstance(second, ConsumerDlqReplayResult)
    assert first.replay_fingerprint != second.replay_fingerprint


@pytest.mark.asyncio
async def test_consumer_dlq_replay_success_audit_failure_is_not_bookkeeping_success() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions", tenant_id=TENANT_ID)
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried_and_queued = AsyncMock(return_value=True)
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        side_effect=RuntimeError("audit database unavailable")
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _consumer_service(
            ingestion_job_service=ingestion_job_service
        )._mark_consumer_dlq_replay_replayed(
            event_id="dlq-001",
            correlation_id="corr-001",
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.detail["code"] == "INGESTION_REPLAY_AUDIT_WRITE_FAILED"
    assert exc_info.value.detail["replay_status"] == "replayed"
    assert ingestion_job_service.record_consumer_dlq_replay_audit.await_count == 1


@pytest.mark.asyncio
async def test_consumer_dlq_replay_publish_failure_records_only_source_safe_reason() -> None:
    context = _replay_context()
    ingestion_job_service = MagicMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-failed")
    replay_payload_dispatcher = MagicMock()
    replay_payload_dispatcher.replay_payload = AsyncMock(
        side_effect=RuntimeError("broker://user:credential@host private-request-value")
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _consumer_service(
            ingestion_job_service=ingestion_job_service,
            replay_payload_dispatcher=replay_payload_dispatcher,
        )._publish_consumer_dlq_replay(
            event_id="dlq-001",
            correlation_id="corr-001",
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    safe_reason = "Consumer DLQ replay could not be published to the downstream ingestion pipeline."
    assert exc_info.value.detail == {
        "code": "INGESTION_DLQ_REPLAY_FAILED",
        "message": safe_reason,
        "replay_audit_id": "audit-failed",
    }
    replay_payload_dispatcher.replay_payload.assert_awaited_once_with(
        endpoint=context.endpoint,
        payload=context.request_payload,
        idempotency_key=context.idempotency_key,
        tenant_id=TENANT_ID,
    )
    _, audit_kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert audit_kwargs["replay_reason"] == safe_reason
    assert "credential" not in str(audit_kwargs)


@pytest.mark.asyncio
async def test_consumer_dlq_replay_bookkeeping_conflict_uses_governed_detail() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions", tenant_id=TENANT_ID)
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried_and_queued = AsyncMock(return_value=False)
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        return_value="audit-conflict"
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _consumer_service(
            ingestion_job_service=ingestion_job_service
        )._mark_consumer_dlq_replay_replayed(
            event_id="dlq-001",
            correlation_id="corr-001",
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "INGESTION_DLQ_REPLAY_BOOKKEEPING_CONFLICT",
        "message": (
            "Replay publish succeeded but ingestion job state changed before bookkeeping completed."
        ),
        "replay_audit_id": "audit-conflict",
        "replay_fingerprint": "fp-001",
    }
    ingestion_job_service.mark_retried_and_queued.assert_awaited_once_with(
        "job-001", tenant_id=TENANT_ID
    )


@pytest.mark.asyncio
async def test_consumer_dlq_replay_bookkeeping_failure_records_only_source_safe_reason() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions", tenant_id=TENANT_ID)
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried_and_queued = AsyncMock(
        side_effect=RuntimeError("postgresql://operator:credential@db/private-request-value")
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        return_value="audit-bookkeeping"
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _consumer_service(
            ingestion_job_service=ingestion_job_service
        )._mark_consumer_dlq_replay_replayed(
            event_id="dlq-001",
            correlation_id="corr-001",
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            requested_by="ops",
        )

    safe_reason = "Replay publish succeeded but post-publish bookkeeping did not complete."
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "INGESTION_DLQ_REPLAY_BOOKKEEPING_FAILED",
        "message": safe_reason,
        "replay_audit_id": "audit-bookkeeping",
        "replay_fingerprint": "fp-001",
    }
    _, audit_kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert audit_kwargs["replay_status"] == "replayed_bookkeeping_failed"
    assert audit_kwargs["replay_reason"] == safe_reason
    assert "credential" not in str(audit_kwargs)
    assert "private-request-value" not in str(audit_kwargs)
