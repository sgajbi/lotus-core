from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.event_replay_service.app.application.consumer_dlq_replay_commands import (
    ConsumerDlqReplayCommand,
    ConsumerDlqReplayCommandService,
    ConsumerDlqReplayResult,
)
from src.services.event_replay_service.app.application.replay_command_errors import (
    ReplayCommandError,
)


def _consumer_service(
    *,
    ingestion_job_service: MagicMock | None = None,
    replay_payload_dispatcher: MagicMock | None = None,
) -> ConsumerDlqReplayCommandService:
    return ConsumerDlqReplayCommandService(
        ingestion_job_service=ingestion_job_service or MagicMock(),
        replay_payload_dispatcher=replay_payload_dispatcher or MagicMock(),
    )


@pytest.mark.asyncio
async def test_consumer_dlq_replay_dry_run_records_audit_without_publish() -> None:
    context = SimpleNamespace(
        endpoint="/ingest/transactions",
        request_payload={"transactions": [{"transaction_id": "T1"}]},
        idempotency_key="idem-001",
        submitted_at=datetime(2026, 7, 4, 9, 0),
    )
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_consumer_dlq_event = AsyncMock(
        return_value=SimpleNamespace(event_id="dlq-001", correlation_id="corr-001")
    )
    ingestion_job_service.list_jobs = AsyncMock(
        return_value=(
            [SimpleNamespace(job_id="job-001", correlation_id="corr-001", status="queued")],
            1,
        )
    )
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
        command=ConsumerDlqReplayCommand(dry_run=True, requested_by="ops"),
    )

    assert response.replay_status == "dry_run"
    assert response.job_id == "job-001"
    assert response.replay_audit_id == "audit-001"
    replay_payload_dispatcher.replay_payload.assert_not_awaited()


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
    ingestion_job_service.list_jobs = AsyncMock(return_value=([], 0))
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-001")

    response = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    )._consumer_dlq_replay_candidate_or_result(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=True,
        requested_by="ops",
    )

    assert response.replay_status == "not_replayable"
    assert response.job_id is None
    assert response.message == "No correlated ingestion job found for consumer DLQ event."
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
    ingestion_job_service.list_jobs = AsyncMock(
        return_value=([{"job_id": "job-001", "correlation_id": "corr-001", "status": "failed"}], 1)
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(
        return_value=SimpleNamespace(
            endpoint="/ingest/transactions",
            request_payload=None,
            idempotency_key="idem-001",
        )
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-002")

    response = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    )._consumer_dlq_replay_candidate_or_result(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=False,
        requested_by="ops",
    )

    assert response.replay_status == "not_replayable"
    assert response.job_id == "job-001"
    assert response.message == "Correlated ingestion job does not have durable replay payload."
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_dlq_replay_candidate_returns_replayable_context() -> None:
    context = SimpleNamespace(
        endpoint="/ingest/transactions",
        request_payload={"transactions": [{"transaction_id": "T1"}]},
        idempotency_key="idem-001",
    )
    ingestion_job_service = MagicMock()
    ingestion_job_service.list_jobs = AsyncMock(
        return_value=(
            [SimpleNamespace(job_id="job-001", correlation_id="corr-001", status="queued")],
            1,
        )
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock()

    candidate = await _consumer_service(
        ingestion_job_service=ingestion_job_service
    )._consumer_dlq_replay_candidate_or_result(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=False,
        requested_by="ops",
    )

    assert not isinstance(candidate, ConsumerDlqReplayResult)
    assert candidate.job_id == "job-001"
    assert candidate.context is context
    assert len(candidate.replay_fingerprint) == 64
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumer_dlq_replay_success_audit_failure_is_not_bookkeeping_success() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions")
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried = AsyncMock()
    ingestion_job_service.mark_queued = AsyncMock()
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
