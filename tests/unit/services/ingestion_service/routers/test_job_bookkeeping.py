from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.services.ingestion_service.app.routers.job_bookkeeping import (
    mark_job_queued_after_publish_or_raise,
    post_publish_bookkeeping_failure_detail,
    raise_post_publish_bookkeeping_failure,
)

pytestmark = pytest.mark.asyncio


async def test_raise_post_publish_bookkeeping_failure_records_non_terminal_observation():
    ingestion_job_service = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await raise_post_publish_bookkeeping_failure(
            ingestion_job_service=ingestion_job_service,
            job_id="job_123",
            failure_reason="queue state write failed",
            failure_phase="persist_bookkeeping",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "INGESTION_JOB_BOOKKEEPING_FAILED",
        "message": "Ingestion work completed, but job bookkeeping did not complete afterward.",
        "job_id": "job_123",
        "publish_state": "published",
        "work_state": "published",
        "published_record_count": None,
        "retry_safe": False,
        "recovery_action": "repair_ingestion_job_bookkeeping",
        "recovery_path": "ingestion_job_bookkeeping_repair",
        "supportability_reason_code": "POST_PERSIST_BOOKKEEPING_FAILED",
        "remediation": (
            "Inspect the job failure history, confirm published or persisted work, then run the "
            "governed bookkeeping repair action before client retry."
        ),
    }
    ingestion_job_service.record_failure_observation.assert_awaited_once_with(
        "job_123",
        "queue state write failed",
        failure_phase="persist_bookkeeping",
    )


async def test_post_publish_bookkeeping_failure_detail_reports_publish_state_and_count():
    detail = post_publish_bookkeeping_failure_detail(
        job_id="job_456",
        failure_phase="queue_bookkeeping",
        published_record_count=3,
    )

    assert detail["publish_state"] == "published"
    assert detail["work_state"] == "published"
    assert detail["published_record_count"] == 3
    assert detail["retry_safe"] is False
    assert detail["supportability_reason_code"] == "POST_PUBLISH_BOOKKEEPING_FAILED"


async def test_mark_job_queued_after_publish_records_rejected_transition():
    ingestion_job_service = AsyncMock()
    ingestion_job_service.mark_queued.return_value = False

    with pytest.raises(HTTPException) as exc_info:
        await mark_job_queued_after_publish_or_raise(
            ingestion_job_service=ingestion_job_service,
            job_id="job_rejected",
            published_record_count=2,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "INGESTION_JOB_BOOKKEEPING_FAILED"
    assert exc_info.value.detail["published_record_count"] == 2
    ingestion_job_service.record_failure_observation.assert_awaited_once_with(
        "job_rejected",
        "job queue transition was rejected",
        failure_phase="queue_bookkeeping",
    )
