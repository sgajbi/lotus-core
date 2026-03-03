from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.services import ingestion_job_service as service_module
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def service() -> IngestionJobService:
    return IngestionJobService()


async def test_assert_retry_allowed_for_records_blocks_large_replay(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    now = datetime.now(UTC)
    monkeypatch.setattr(
        service_module,
        "REPLAY_MAX_RECORDS_PER_REQUEST",
        2,
    )
    async def _mock_get_ops_mode() -> SimpleNamespace:
        return SimpleNamespace(mode="normal", replay_window_start=None, replay_window_end=None)

    async def _mock_count_backlog_jobs() -> int:
        return 0

    monkeypatch.setattr(service, "get_ops_mode", _mock_get_ops_mode)
    monkeypatch.setattr(service, "_count_backlog_jobs", _mock_count_backlog_jobs)

    with pytest.raises(PermissionError, match="requested replay record count exceeds configured limit"):
        await service.assert_retry_allowed_for_records(
            submitted_at=now - timedelta(minutes=1),
            replay_record_count=3,
        )


async def test_assert_retry_allowed_for_records_blocks_when_backlog_high(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    now = datetime.now(UTC)
    monkeypatch.setattr(service_module, "REPLAY_MAX_RECORDS_PER_REQUEST", 100)
    monkeypatch.setattr(service_module, "REPLAY_MAX_BACKLOG_JOBS", 5)
    async def _mock_get_ops_mode() -> SimpleNamespace:
        return SimpleNamespace(mode="normal", replay_window_start=None, replay_window_end=None)

    async def _mock_count_backlog_jobs() -> int:
        return 5

    monkeypatch.setattr(service, "get_ops_mode", _mock_get_ops_mode)
    monkeypatch.setattr(service, "_count_backlog_jobs", _mock_count_backlog_jobs)

    with pytest.raises(PermissionError, match="backlog exceeds configured replay safety threshold"):
        await service.assert_retry_allowed_for_records(
            submitted_at=now - timedelta(minutes=1),
            replay_record_count=1,
        )


async def test_assert_reprocessing_publish_allowed_reuses_retry_guardrails(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    called: dict[str, int] = {"count": 0}

    async def _mock_guardrail(*, submitted_at: datetime, replay_record_count: int) -> None:
        called["count"] += 1
        assert replay_record_count == 7
        assert submitted_at.tzinfo is not None

    monkeypatch.setattr(service, "assert_retry_allowed_for_records", _mock_guardrail)
    await service.assert_reprocessing_publish_allowed(7)
    assert called["count"] == 1
