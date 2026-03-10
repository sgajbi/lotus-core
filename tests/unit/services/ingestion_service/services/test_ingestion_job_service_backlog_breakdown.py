from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.services.ingestion_service.app.services import ingestion_job_service as service_module
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService

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


async def test_get_backlog_breakdown_computes_groups_and_concentration(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)

    class _FakeResult:
        def all(self):
            return [
                ("/ingest/transactions", "transaction", 100, 4, 2, 3, now - timedelta(minutes=10)),
                ("/ingest/market-prices", "market_price", 70, 3, 1, 1, now - timedelta(minutes=5)),
                ("/ingest/instruments", "instrument", 40, 1, 0, 2, now - timedelta(minutes=2)),
            ]

    class _FakeSession:
        async def scalar(self, _stmt):
            return 11

        async def execute(self, _stmt):
            return _FakeResult()

    def _mock_get_async_db_session():
        return _SingleSessionAsyncIterator(_FakeSession())

    monkeypatch.setattr(service_module, "get_async_db_session", _mock_get_async_db_session)

    result = await service.get_backlog_breakdown(lookback_minutes=60, limit=10)

    assert result.total_backlog_jobs == 11
    assert result.largest_group_backlog_jobs == 6
    assert result.largest_group_backlog_share == Decimal("0.5454545454545454545454545455")
    assert result.top_3_backlog_share == Decimal("1")
    assert len(result.groups) == 3
    assert result.groups[0].endpoint == "/ingest/transactions"
    assert result.groups[0].backlog_jobs == 6


async def test_get_backlog_breakdown_zero_backlog_has_zero_concentration(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResult:
        def all(self):
            return []

    class _FakeSession:
        async def scalar(self, _stmt):
            return 0

        async def execute(self, _stmt):
            return _FakeResult()

    def _mock_get_async_db_session():
        return _SingleSessionAsyncIterator(_FakeSession())

    monkeypatch.setattr(service_module, "get_async_db_session", _mock_get_async_db_session)

    result = await service.get_backlog_breakdown(lookback_minutes=60, limit=10)

    assert result.total_backlog_jobs == 0
    assert result.largest_group_backlog_jobs == 0
    assert result.largest_group_backlog_share == Decimal("0")
    assert result.top_3_backlog_share == Decimal("0")
    assert result.groups == []
