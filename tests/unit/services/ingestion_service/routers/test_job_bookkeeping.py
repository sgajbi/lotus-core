from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.services.ingestion_service.app.routers.job_bookkeeping import (
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
    assert exc_info.value.detail["code"] == "INGESTION_JOB_BOOKKEEPING_FAILED"
    assert exc_info.value.detail["job_id"] == "job_123"
    ingestion_job_service.record_failure_observation.assert_awaited_once_with(
        "job_123",
        "queue state write failed",
        failure_phase="persist_bookkeeping",
    )
