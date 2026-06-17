from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.services.ingestion_stalled_jobs import (
    load_stalled_job_list_response,
    stalled_job_suggested_action,
    to_stalled_job_response,
)

pytestmark = pytest.mark.asyncio


class _SingleSessionAsyncIterator:
    def __init__(self, session):
        self._session = session
        self._yielded = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return self._session


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _job(**overrides):
    values = {
        "job_id": "job-1",
        "endpoint": "/ingest/transactions",
        "entity_type": "transaction",
        "status": "accepted",
        "submitted_at": datetime(2026, 6, 17, 0, 0, tzinfo=UTC),
        "retry_count": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def test_to_stalled_job_response_preserves_queue_age_and_action() -> None:
    now = datetime(2026, 6, 17, 0, 5, tzinfo=UTC)

    response = to_stalled_job_response(_job(), now=now)

    assert response.job_id == "job-1"
    assert response.queue_age_seconds == 300.0
    assert response.suggested_action == stalled_job_suggested_action("accepted")


async def test_stalled_job_suggested_action_distinguishes_queued_jobs() -> None:
    assert stalled_job_suggested_action("queued").startswith(
        "Inspect downstream processing bottlenecks"
    )


async def test_load_stalled_job_list_response_maps_ordered_rows() -> None:
    now = datetime(2026, 6, 17, 0, 10, tzinfo=UTC)

    class _FakeSession:
        async def scalars(self, _stmt):
            return _FakeScalars(
                [
                    _job(
                        job_id="job-1", status="accepted", submitted_at=now - timedelta(minutes=7)
                    ),
                    _job(job_id="job-2", status="queued", submitted_at=now - timedelta(minutes=5)),
                ]
            )

    response = await load_stalled_job_list_response(
        threshold_seconds=300,
        limit=50,
        now=now,
        session_factory=lambda: _SingleSessionAsyncIterator(_FakeSession()),
    )

    assert response.threshold_seconds == 300
    assert response.total == 2
    assert [job.job_id for job in response.jobs] == ["job-1", "job-2"]
    assert response.jobs[0].queue_age_seconds == 420.0
    assert response.jobs[1].suggested_action.startswith("Inspect downstream processing bottlenecks")
