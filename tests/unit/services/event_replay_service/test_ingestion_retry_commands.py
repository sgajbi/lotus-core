from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.event_replay_service.app.application.ingestion_retry_commands import (
    IngestionRetryCommandService,
)
from src.services.event_replay_service.app.application.replay_command_errors import (
    ReplayCommandError,
)
from src.services.ingestion_service.app.DTOs.ingestion_job_dto import IngestionRetryRequest


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
        idempotency_key="idem-001",
        submitted_at=datetime(2026, 7, 4, 9, 0),
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
        job_id="job-001",
        retry_request=IngestionRetryRequest(dry_run=True, record_keys=["T1"]),
        requested_by="ops",
    )

    assert response is job
    replay_payload_dispatcher.replay_payload.assert_not_awaited()
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()
    _, audit_kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert audit_kwargs["replay_status"] == "dry_run"
    assert audit_kwargs["alternate_lookup_key"] == "job:job-001"


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
        )._required_job_replay_context("job-missing")

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
        )._required_job_replay_context("job-no-payload")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INGESTION_JOB_RETRY_UNSUPPORTED"
    assert exc_info.value.detail["outcome"] == "retry_unsupported"
    assert "durable replay payload" in exc_info.value.detail["remediation"]


def test_ingestion_job_retry_partial_unsupported_uses_recovery_detail() -> None:
    context = SimpleNamespace(
        endpoint="/ingest/market-prices",
        request_payload={"market_prices": [{"security_id": "S1"}]},
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
    ingestion_job_service.mark_failed = AsyncMock()
    replay_payload_dispatcher = MagicMock()
    replay_payload_dispatcher.replay_payload = AsyncMock(
        side_effect=RuntimeError("broker timeout with sensitive downstream detail")
    )

    with pytest.raises(ReplayCommandError) as exc_info:
        await _retry_service(
            ingestion_job_service=ingestion_job_service,
            replay_payload_dispatcher=replay_payload_dispatcher,
        )._publish_ingestion_job_retry(
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
    ingestion_job_service.mark_failed.assert_awaited_once()
    _, mark_failed_args = ingestion_job_service.mark_failed.await_args
    assert mark_failed_args["failure_phase"] == "retry_publish"
    assert mark_failed_args["failed_record_keys"] == ["T1"]


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
    ingestion_job_service.mark_retried_and_queued.assert_awaited_once_with("job-001")
