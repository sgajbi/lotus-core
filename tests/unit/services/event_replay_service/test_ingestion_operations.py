import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.services.event_replay_service.app.application.replay_payload_dispatcher import (
    IngestionServiceReplayPayloadDispatcher,
)
from src.services.event_replay_service.app.routers.ingestion_operations import (
    _assert_ingestion_retry_allowed,
    _block_duplicate_ingestion_job_retry,
    _bookkeeping_repair_phase_or_http_error,
    _bookkeeping_repair_response,
    _consumer_dlq_not_replayable_response,
    _consumer_dlq_replay_candidate_or_response,
    _filter_payload_by_record_keys,
    _mark_consumer_dlq_replay_replayed,
    _mark_ingestion_job_queued_for_bookkeeping_repair,
    _mark_ingestion_job_retry_replayed,
    _publish_ingestion_job_retry,
    _record_mandatory_replay_audit,
    _required_ingestion_job_for_bookkeeping_repair,
    _required_job_replay_context,
    _retry_payload_or_http_error,
)
from src.services.ingestion_service.app.DTOs.ingestion_job_dto import IngestionRetryRequest

REPO_ROOT = Path(__file__).resolve().parents[4]


def _copy_package_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )


def test_event_replay_app_imports_under_compose_runtime_layout(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    _copy_package_tree(
        REPO_ROOT / "src" / "services" / "event_replay_service" / "app",
        runtime_root / "app",
    )
    _copy_package_tree(
        REPO_ROOT / "src" / "services" / "ingestion_service" / "app",
        runtime_root / "src" / "services" / "ingestion_service" / "app",
    )

    python_path = os.pathsep.join(
        [
            str(runtime_root),
            str(REPO_ROOT / "src" / "libs" / "portfolio-common"),
        ]
    )
    env = {**os.environ, "PYTHONPATH": python_path}

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=runtime_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr


def test_filter_payload_by_record_keys_returns_original_payload_without_record_keys() -> None:
    payload = {"transactions": [{"transaction_id": "T1"}]}

    filtered = _filter_payload_by_record_keys(
        endpoint="/ingest/transactions",
        payload=payload,
        record_keys=[],
    )

    assert filtered is payload


@pytest.mark.parametrize(
    ("endpoint", "payload", "record_keys", "expected"),
    [
        (
            "/ingest/transactions",
            {"transactions": [{"transaction_id": "T1"}, {"transaction_id": "T2"}]},
            ["T2"],
            {"transactions": [{"transaction_id": "T2"}]},
        ),
        (
            "/ingest/portfolios",
            {"portfolios": [{"portfolio_id": "P1"}, {"portfolio_id": "P2"}]},
            ["P1"],
            {"portfolios": [{"portfolio_id": "P1"}]},
        ),
        (
            "/ingest/instruments",
            {"instruments": [{"security_id": "S1"}, {"security_id": "S2"}]},
            ["S2"],
            {"instruments": [{"security_id": "S2"}]},
        ),
        (
            "/ingest/business-dates",
            {"business_dates": [{"business_date": date(2026, 6, 22)}]},
            ["2026-06-22"],
            {"business_dates": [{"business_date": date(2026, 6, 22)}]},
        ),
        (
            "/reprocess/transactions",
            {"transaction_ids": ["T1", "T2", "T3"]},
            ["T1", "T3"],
            {"transaction_ids": ["T1", "T3"]},
        ),
    ],
)
def test_filter_payload_by_record_keys_filters_supported_partial_retry_payloads(
    endpoint: str,
    payload: dict,
    record_keys: list[str],
    expected: dict,
) -> None:
    assert (
        _filter_payload_by_record_keys(
            endpoint=endpoint,
            payload=payload,
            record_keys=record_keys,
        )
        == expected
    )


def test_filter_payload_by_record_keys_rejects_unsupported_partial_retry_endpoint() -> None:
    with pytest.raises(ValueError, match="Partial retry is not supported"):
        _filter_payload_by_record_keys(
            endpoint="/ingest/market-prices",
            payload={"market_prices": [{"security_id": "S1"}]},
            record_keys=["S1"],
        )


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_dispatches_list_field_payload_with_idempotency_key() -> (
    None
):
    ingestion_service = MagicMock()
    ingestion_service.publish_business_dates = AsyncMock()

    dispatcher = IngestionServiceReplayPayloadDispatcher(ingestion_service)

    await dispatcher.replay_payload(
        endpoint="/ingest/business-dates",
        payload={"business_dates": [{"business_date": "2026-06-22"}]},
        idempotency_key="idem-001",
    )

    ingestion_service.publish_business_dates.assert_awaited_once()
    args, kwargs = ingestion_service.publish_business_dates.await_args
    assert [business_date.business_date for business_date in args[0]] == [date(2026, 6, 22)]
    assert kwargs == {"idempotency_key": "idem-001"}


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_dispatches_whole_portfolio_bundle_request() -> None:
    ingestion_service = MagicMock()
    ingestion_service.publish_portfolio_bundle = AsyncMock()

    dispatcher = IngestionServiceReplayPayloadDispatcher(ingestion_service)

    await dispatcher.replay_payload(
        endpoint="/ingest/portfolio-bundle",
        payload={"business_dates": [{"business_date": "2026-06-22"}]},
        idempotency_key="idem-002",
    )

    ingestion_service.publish_portfolio_bundle.assert_awaited_once()
    args, kwargs = ingestion_service.publish_portfolio_bundle.await_args
    assert args[0].business_dates[0].business_date == date(2026, 6, 22)
    assert kwargs == {"idempotency_key": "idem-002"}


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_rejects_unsupported_endpoint() -> None:
    dispatcher = IngestionServiceReplayPayloadDispatcher(MagicMock())

    with pytest.raises(ValueError, match="Retry not supported"):
        await dispatcher.replay_payload(
            endpoint="/ingest/not-supported",
            payload={},
            idempotency_key=None,
        )


@pytest.mark.asyncio
async def test_mandatory_replay_audit_returns_replay_id() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-123")

    replay_id = await _record_mandatory_replay_audit(
        ingestion_job_service=ingestion_job_service,
        recovery_path="ingestion_job_retry",
        event_id="job:job-123",
        replay_fingerprint="fp-123",
        correlation_id=None,
        job_id="job-123",
        endpoint="/ingest/transactions",
        replay_status="dry_run",
        dry_run=True,
        replay_reason="dry-run",
        requested_by="ops",
        correlation_missing_reason="ingestion_job_retry_uses_job_id",
        alternate_lookup_key="job:job-123",
    )

    assert replay_id == "audit-123"
    _, kwargs = ingestion_job_service.record_consumer_dlq_replay_audit.await_args
    assert kwargs["correlation_missing_reason"] == "ingestion_job_retry_uses_job_id"
    assert kwargs["alternate_lookup_key"] == "job:job-123"


@pytest.mark.asyncio
async def test_mandatory_replay_audit_failure_raises_governed_error() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )

    with pytest.raises(HTTPException) as exc_info:
        await _record_mandatory_replay_audit(
            ingestion_job_service=ingestion_job_service,
            recovery_path="consumer_dlq_replay",
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
async def test_bookkeeping_repair_requires_existing_job() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await _required_ingestion_job_for_bookkeeping_repair(
            ingestion_job_service=ingestion_job_service,
            job_id="job-missing",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "INGESTION_JOB_NOT_FOUND",
        "message": "Ingestion job 'job-missing' was not found.",
    }


def test_bookkeeping_repair_phase_requires_failure_evidence_and_eligible_status() -> None:
    failures = [SimpleNamespace(failure_phase="queue_bookkeeping")]

    assert (
        _bookkeeping_repair_phase_or_http_error(
            failures=failures,
            job_id="job-123",
            previous_status="accepted",
        )
        == "queue_bookkeeping"
    )

    with pytest.raises(HTTPException) as exc_info:
        _bookkeeping_repair_phase_or_http_error(
            failures=[],
            job_id="job-123",
            previous_status="accepted",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "INGESTION_BOOKKEEPING_REPAIR_NOT_ELIGIBLE",
        "message": "Ingestion job is not eligible for bookkeeping repair.",
        "job_id": "job-123",
        "status": "accepted",
    }

    with pytest.raises(HTTPException) as status_exc_info:
        _bookkeeping_repair_phase_or_http_error(
            failures=failures,
            job_id="job-123",
            previous_status="failed",
        )

    assert status_exc_info.value.status_code == 409
    assert status_exc_info.value.detail["status"] == "failed"


@pytest.mark.asyncio
async def test_bookkeeping_repair_mark_queued_failure_uses_governed_error() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_queued = AsyncMock(side_effect=RuntimeError("db down"))

    with pytest.raises(HTTPException) as exc_info:
        await _mark_ingestion_job_queued_for_bookkeeping_repair(
            ingestion_job_service=ingestion_job_service,
            job_id="job-123",
            previous_status="accepted",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "INGESTION_BOOKKEEPING_REPAIR_FAILED",
        "message": "Ingestion job bookkeeping repair did not complete.",
        "job_id": "job-123",
        "recovery_action": "repair_ingestion_job_bookkeeping",
    }


def test_bookkeeping_repair_response_maps_supportability_reason() -> None:
    response = _bookkeeping_repair_response(
        job_id="job-123",
        previous_status="accepted",
        repaired_status="queued",
        bookkeeping_phase="queue_bookkeeping",
    )

    assert response.job_id == "job-123"
    assert response.previous_status == "accepted"
    assert response.repaired_status == "queued"
    assert response.recovery_action == "repair_ingestion_job_bookkeeping"
    assert response.supportability_reason_code == "POST_PUBLISH_BOOKKEEPING_FAILED"
    assert response.retry_safe is False
    assert response.message == "Ingestion job bookkeeping repaired from accepted to queued."


@pytest.mark.asyncio
async def test_consumer_dlq_replay_candidate_records_no_correlated_job_response() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.list_jobs = AsyncMock(return_value=([], 0))
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-001")

    response = await _consumer_dlq_replay_candidate_or_response(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=True,
        ingestion_job_service=ingestion_job_service,
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

    response = await _consumer_dlq_not_replayable_response(
        event_id="dlq-003",
        correlation_id=None,
        correlation_missing_reason="message_correlation_id_absent",
        alternate_lookup_key="consumer_dlq|topic=transactions.raw.received|event=dlq-003",
        job_id=None,
        endpoint=None,
        dry_run=True,
        replay_reason="DLQ event has no correlation id.",
        ingestion_job_service=ingestion_job_service,
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

    response = await _consumer_dlq_replay_candidate_or_response(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=False,
        ingestion_job_service=ingestion_job_service,
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

    (
        replay_job_id,
        replay_context,
        replay_fingerprint,
    ) = await _consumer_dlq_replay_candidate_or_response(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=False,
        ingestion_job_service=ingestion_job_service,
        requested_by="ops",
    )

    assert replay_job_id == "job-001"
    assert replay_context is context
    assert len(replay_fingerprint) == 64
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingestion_job_retry_success_audit_failure_is_not_bookkeeping_success() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions")
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried = AsyncMock()
    ingestion_job_service.mark_queued = AsyncMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        side_effect=RuntimeError("audit database unavailable")
    )

    with pytest.raises(HTTPException) as exc_info:
        await _mark_ingestion_job_retry_replayed(
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            ingestion_job_service=ingestion_job_service,
            ops_actor="ops",
        )

    assert exc_info.value.detail["code"] == "INGESTION_REPLAY_AUDIT_WRITE_FAILED"
    assert exc_info.value.detail["replay_status"] == "replayed"
    assert ingestion_job_service.record_consumer_dlq_replay_audit.await_count == 1


@pytest.mark.asyncio
async def test_ingestion_job_retry_not_found_uses_governed_recovery_detail() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await _required_job_replay_context("job-missing", ingestion_job_service)

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

    with pytest.raises(HTTPException) as exc_info:
        await _required_job_replay_context("job-no-payload", ingestion_job_service)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INGESTION_JOB_RETRY_UNSUPPORTED"
    assert exc_info.value.detail["outcome"] == "retry_unsupported"
    assert "durable replay payload" in exc_info.value.detail["remediation"]


def test_ingestion_job_retry_partial_unsupported_uses_recovery_detail() -> None:
    context = SimpleNamespace(
        endpoint="/ingest/market-prices",
        request_payload={"market_prices": [{"security_id": "S1"}]},
    )

    with pytest.raises(HTTPException) as exc_info:
        _retry_payload_or_http_error(
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

    with pytest.raises(HTTPException) as exc_info:
        await _assert_ingestion_retry_allowed(
            ingestion_job_service=ingestion_job_service,
            submitted_at=SimpleNamespace(),
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

    with pytest.raises(HTTPException) as exc_info:
        await _block_duplicate_ingestion_job_retry(
            job_id="job-001",
            context=context,
            ingestion_job_service=ingestion_job_service,
            replay_fingerprint="fp-001",
            ops_actor="ops",
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

    with pytest.raises(HTTPException) as exc_info:
        await _block_duplicate_ingestion_job_retry(
            job_id="job-001",
            context=context,
            ingestion_job_service=ingestion_job_service,
            replay_fingerprint="fp-001",
            ops_actor="ops",
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

    with pytest.raises(HTTPException) as exc_info:
        await _publish_ingestion_job_retry(
            job_id="job-001",
            context=context,
            retry_request=IngestionRetryRequest(record_keys=["T1"]),
            replay_payload={"transactions": [{"transaction_id": "T1"}]},
            replay_fingerprint="fp-001",
            ingestion_job_service=ingestion_job_service,
            replay_payload_dispatcher=replay_payload_dispatcher,
            ops_actor="ops",
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
    ingestion_job_service.mark_retried = AsyncMock()
    ingestion_job_service.mark_queued = AsyncMock(
        side_effect=RuntimeError("queue state write failed with downstream detail")
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-book")

    with pytest.raises(HTTPException) as exc_info:
        await _mark_ingestion_job_retry_replayed(
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            ingestion_job_service=ingestion_job_service,
            ops_actor="ops",
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
async def test_consumer_dlq_replay_success_audit_failure_is_not_bookkeeping_success() -> None:
    context = SimpleNamespace(endpoint="/ingest/transactions")
    ingestion_job_service = MagicMock()
    ingestion_job_service.mark_retried = AsyncMock()
    ingestion_job_service.mark_queued = AsyncMock()
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(
        side_effect=RuntimeError("audit database unavailable")
    )

    with pytest.raises(HTTPException) as exc_info:
        await _mark_consumer_dlq_replay_replayed(
            event_id="dlq-001",
            correlation_id="corr-001",
            job_id="job-001",
            context=context,
            replay_fingerprint="fp-001",
            ingestion_job_service=ingestion_job_service,
            requested_by="ops",
        )

    assert exc_info.value.detail["code"] == "INGESTION_REPLAY_AUDIT_WRITE_FAILED"
    assert exc_info.value.detail["replay_status"] == "replayed"
    assert ingestion_job_service.record_consumer_dlq_replay_audit.await_count == 1
