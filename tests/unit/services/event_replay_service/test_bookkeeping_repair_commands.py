from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.event_replay_service.app.application.bookkeeping_repair_commands import (
    BookkeepingRepairCommandError,
    BookkeepingRepairCommandService,
)


def _repair_service(
    *,
    ingestion_job_service: MagicMock | None = None,
) -> BookkeepingRepairCommandService:
    return BookkeepingRepairCommandService(
        ingestion_job_service=ingestion_job_service or MagicMock()
    )


@pytest.mark.asyncio
async def test_bookkeeping_repair_marks_accepted_job_queued_and_returns_result() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(
        side_effect=[
            SimpleNamespace(job_id="job-123", status="accepted"),
            SimpleNamespace(job_id="job-123", status="queued"),
        ]
    )
    ingestion_job_service.list_failures = AsyncMock(
        return_value=[SimpleNamespace(failure_phase="queue_bookkeeping")]
    )
    ingestion_job_service.mark_queued = AsyncMock()

    response = await _repair_service(
        ingestion_job_service=ingestion_job_service
    ).repair_ingestion_job_bookkeeping("job-123")

    assert response.job_id == "job-123"
    assert response.previous_status == "accepted"
    assert response.repaired_status == "queued"
    assert response.recovery_action == "repair_ingestion_job_bookkeeping"
    assert response.supportability_reason_code == "POST_PUBLISH_BOOKKEEPING_FAILED"
    assert response.retry_safe is False
    assert response.message == "Ingestion job bookkeeping repaired from accepted to queued."
    ingestion_job_service.mark_queued.assert_awaited_once_with("job-123")


@pytest.mark.asyncio
async def test_bookkeeping_repair_leaves_already_queued_job_unchanged() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(
        return_value=SimpleNamespace(job_id="job-123", status="queued")
    )
    ingestion_job_service.list_failures = AsyncMock(
        return_value=[SimpleNamespace(failure_phase="persist_bookkeeping")]
    )
    ingestion_job_service.mark_queued = AsyncMock()

    response = await _repair_service(
        ingestion_job_service=ingestion_job_service
    ).repair_ingestion_job_bookkeeping("job-123")

    assert response.previous_status == "queued"
    assert response.repaired_status == "queued"
    assert response.supportability_reason_code == "POST_PERSIST_BOOKKEEPING_FAILED"
    ingestion_job_service.mark_queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_bookkeeping_repair_requires_existing_job() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(return_value=None)

    with pytest.raises(BookkeepingRepairCommandError) as exc_info:
        await _repair_service(
            ingestion_job_service=ingestion_job_service
        )._required_ingestion_job_for_bookkeeping_repair("job-missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "INGESTION_JOB_NOT_FOUND",
        "message": "Ingestion job 'job-missing' was not found.",
    }


def test_bookkeeping_repair_phase_requires_failure_evidence_and_eligible_status() -> None:
    service = _repair_service()
    failures = [SimpleNamespace(failure_phase="queue_bookkeeping")]

    assert (
        service._bookkeeping_repair_phase_or_error(
            failures=failures,
            job_id="job-123",
            previous_status="accepted",
        )
        == "queue_bookkeeping"
    )

    with pytest.raises(BookkeepingRepairCommandError) as exc_info:
        service._bookkeeping_repair_phase_or_error(
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

    with pytest.raises(BookkeepingRepairCommandError) as status_exc_info:
        service._bookkeeping_repair_phase_or_error(
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

    with pytest.raises(BookkeepingRepairCommandError) as exc_info:
        await _repair_service(
            ingestion_job_service=ingestion_job_service
        )._mark_ingestion_job_queued_for_bookkeeping_repair(
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


def test_bookkeeping_repair_result_maps_supportability_reason() -> None:
    response = BookkeepingRepairCommandService._bookkeeping_repair_result(
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
