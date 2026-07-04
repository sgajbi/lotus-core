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
    _bookkeeping_repair_phase_or_http_error,
    _bookkeeping_repair_response,
    _mark_ingestion_job_queued_for_bookkeeping_repair,
    _required_ingestion_job_for_bookkeeping_repair,
)

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
