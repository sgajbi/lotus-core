from datetime import UTC, datetime, timedelta

import pytest
from portfolio_common.database_models import ReprocessingJob
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.services.ingestion_reprocessing_queue_health import (
    load_reprocessing_queue_health_response,
)

pytestmark = pytest.mark.asyncio


async def test_queue_health_excludes_completed_only_history(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="ACTIVE_QUEUE",
                payload={"scope": "pending"},
                status="PENDING",
                created_at=now - timedelta(minutes=5),
            ),
            ReprocessingJob(
                job_type="ACTIVE_QUEUE",
                payload={"scope": "processing"},
                status="PROCESSING",
                lease_owner="queue-health-worker",
                lease_token="e" * 32,
                lease_expires_at=now + timedelta(minutes=15),
            ),
            ReprocessingJob(
                job_type="ACTIVE_QUEUE",
                payload={"scope": "failed"},
                status="FAILED",
            ),
            ReprocessingJob(
                job_type="ACTIVE_QUEUE",
                payload={"scope": "complete"},
                status="COMPLETE",
            ),
            ReprocessingJob(
                job_type="COMPLETED_ONLY_QUEUE",
                payload={"scope": "complete"},
                status="COMPLETE",
            ),
        ]
    )
    await async_db_session.commit()

    async def session_factory():
        yield async_db_session

    response = await load_reprocessing_queue_health_response(
        session_factory=session_factory,
    )

    assert response.total_pending_jobs == 1
    assert response.total_processing_jobs == 1
    assert response.total_failed_jobs == 1
    assert len(response.queues) == 1
    assert response.queues[0].job_type == "ACTIVE_QUEUE"
    assert response.queues[0].pending_jobs == 1
    assert response.queues[0].processing_jobs == 1
    assert response.queues[0].failed_jobs == 1
    assert response.queues[0].oldest_pending_created_at == now - timedelta(minutes=5)
