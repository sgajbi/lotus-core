from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.services.ingestion_service.app.services import ingestion_job_service as service_module
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
    _derive_capacity_group,
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


@pytest.fixture
def service() -> IngestionJobService:
    return IngestionJobService()


async def test_derive_capacity_group_marks_over_capacity_when_utilization_exceeds_one() -> None:
    result = _derive_capacity_group(
        endpoint="/ingest/transactions",
        entity_type="transaction",
        total_records=720,
        processed_records=360,
        backlog_records=120,
        backlog_jobs=3,
        lookback_seconds=Decimal("60"),
        assumed_replicas=1,
    )

    assert result.lambda_in_events_per_second == Decimal("12")
    assert result.mu_msg_per_replica_events_per_second == Decimal("6")
    assert result.effective_capacity_events_per_second == Decimal("6")
    assert result.utilization_ratio == Decimal("2")
    assert result.headroom_ratio == Decimal("-1")
    assert result.saturation_state == "over_capacity"
    assert result.estimated_drain_seconds is None


async def test_get_capacity_status_aggregates_groups(service: IngestionJobService, monkeypatch):
    class _FakeSession:
        async def execute(self, _stmt):
            return [
                ("/ingest/transactions", "transaction", 1200, 900, 300, 6),
                ("/ingest/instruments", "instrument", 200, 200, 0, 0),
            ]

    def _mock_get_async_db_session():
        return _SingleSessionAsyncIterator(_FakeSession())

    monkeypatch.setattr(service_module, "get_async_db_session", _mock_get_async_db_session)

    result = await service.get_capacity_status(
        lookback_minutes=60,
        limit=10,
        assumed_replicas=2,
    )

    assert result.lookback_minutes == 60
    assert result.assumed_replicas == 2
    assert result.total_groups == 2
    assert result.total_backlog_records == 300
    assert result.as_of <= datetime.now(UTC)

    first = result.groups[0]
    assert first.endpoint == "/ingest/transactions"
    assert first.total_records == 1200
    assert first.processed_records == 900
    assert first.backlog_records == 300
    assert first.lambda_in_events_per_second == Decimal("0.3333333333333333333333333333")
    assert first.mu_msg_per_replica_events_per_second == Decimal("0.25")
    assert first.effective_capacity_events_per_second == Decimal("0.50")
    assert first.utilization_ratio == Decimal("0.6666666666666666666666666666")
    assert first.saturation_state == "stable"
    assert first.estimated_drain_seconds is not None
