from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.services import ingestion_job_service as service_module
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
    OperatingBandPolicy,
    OperatingBandSignals,
    classify_operating_band,
)

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


async def test_get_error_budget_status_includes_pressure_ratios(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeBegin:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FakeResult:
        def __init__(self, *, row: tuple | None = None, scalar: int | None = None):
            self._row = row
            self._scalar = scalar

        def one(self):
            assert self._row is not None
            return self._row

        def scalar_one(self):
            assert self._scalar is not None
            return self._scalar

    class _FakeSession:
        def __init__(self):
            self.calls = 0

        async def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return _FakeResult(row=(100, 5, 20))
            if self.calls == 2:
                return _FakeResult(row=(10,))
            if self.calls == 3:
                return _FakeResult(scalar=4)
            raise AssertionError("Unexpected execute call count")

        def begin(self):
            return _FakeBegin()

    async def _mock_get_async_db_session():
        yield _FakeSession()

    monkeypatch.setattr(service_module, "get_async_db_session", _mock_get_async_db_session)
    monkeypatch.setattr(service_module, "REPLAY_MAX_BACKLOG_JOBS", 5000)
    monkeypatch.setattr(service_module, "DLQ_BUDGET_EVENTS_PER_WINDOW", 10)

    result = await service.get_error_budget_status()
    assert result.failure_rate == Decimal("0.05")
    assert result.replay_backlog_pressure_ratio == Decimal("0.004")
    assert result.dlq_events_in_window == 4
    assert result.dlq_budget_events_per_window == 10
    assert result.dlq_pressure_ratio == Decimal("0.4")


async def test_get_operating_band_returns_red_for_high_backlog_or_dlq(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    async def _mock_slo_status(**_kwargs):
        return SimpleNamespace(
            backlog_age_seconds=200.0,
            breach_failure_rate=False,
            breach_queue_latency=False,
            breach_backlog_age=True,
            failure_rate=Decimal("0.01"),
        )

    async def _mock_error_budget_status(**_kwargs):
        return SimpleNamespace(dlq_pressure_ratio=Decimal("1.2"))

    monkeypatch.setattr(service, "get_slo_status", _mock_slo_status)
    monkeypatch.setattr(service, "get_error_budget_status", _mock_error_budget_status)

    result = await service.get_operating_band()
    assert result.operating_band == "red"
    assert "backlog_age_seconds>=180" in result.triggered_signals


async def test_get_operating_band_returns_yellow_for_early_pressure(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    async def _mock_slo_status(**_kwargs):
        return SimpleNamespace(
            backlog_age_seconds=20.0,
            breach_failure_rate=False,
            breach_queue_latency=False,
            breach_backlog_age=False,
            failure_rate=Decimal("0.005"),
        )

    async def _mock_error_budget_status(**_kwargs):
        return SimpleNamespace(dlq_pressure_ratio=Decimal("0.10"))

    monkeypatch.setattr(service, "get_slo_status", _mock_slo_status)
    monkeypatch.setattr(service, "get_error_budget_status", _mock_error_budget_status)

    result = await service.get_operating_band()
    assert result.operating_band == "yellow"
    assert result.recommended_action.startswith("Scale up one band")


async def test_classify_operating_band_policy_yellow_orange_red_ordering():
    policy = OperatingBandPolicy(
        yellow_backlog_age_seconds=10.0,
        orange_backlog_age_seconds=50.0,
        red_backlog_age_seconds=100.0,
        yellow_dlq_pressure_ratio=Decimal("0.20"),
        orange_dlq_pressure_ratio=Decimal("0.40"),
        red_dlq_pressure_ratio=Decimal("0.90"),
    )

    yellow = classify_operating_band(
        signals=OperatingBandSignals(
            backlog_age_seconds=12.0,
            dlq_pressure_ratio=Decimal("0.10"),
            breach_failure_rate=False,
            breach_queue_latency=False,
            breach_backlog_age=False,
            failure_rate=Decimal("0.00"),
        ),
        policy=policy,
    )
    assert yellow.operating_band == "yellow"

    orange = classify_operating_band(
        signals=OperatingBandSignals(
            backlog_age_seconds=55.0,
            dlq_pressure_ratio=Decimal("0.10"),
            breach_failure_rate=False,
            breach_queue_latency=False,
            breach_backlog_age=False,
            failure_rate=Decimal("0.00"),
        ),
        policy=policy,
    )
    assert orange.operating_band == "orange"

    red = classify_operating_band(
        signals=OperatingBandSignals(
            backlog_age_seconds=20.0,
            dlq_pressure_ratio=Decimal("1.10"),
            breach_failure_rate=False,
            breach_queue_latency=False,
            breach_backlog_age=False,
            failure_rate=Decimal("0.00"),
        ),
        policy=policy,
    )
    assert red.operating_band == "red"


async def test_get_operating_policy_returns_configured_thresholds(
    service: IngestionJobService,
):
    policy = await service.get_operating_policy()
    assert policy.policy_version == "v1"
    assert len(policy.policy_fingerprint) == 16
    assert all(char in "0123456789abcdef" for char in policy.policy_fingerprint)
    assert policy.lookback_minutes_default >= 1
    assert policy.replay_max_records_per_request >= 1
    assert policy.replay_max_backlog_jobs >= 1
    assert policy.dlq_budget_events_per_window >= 1


async def test_get_reprocessing_queue_health_aggregates_by_job_type(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeBegin:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FakeResult:
        def mappings(self):
            return self

        def all(self):
            now = datetime.now(UTC)
            return [
                {
                    "job_type": "RESET_WATERMARKS",
                    "pending_jobs": 3,
                    "processing_jobs": 1,
                    "failed_jobs": 0,
                    "oldest_pending_created_at": now - timedelta(seconds=30),
                },
                {
                    "job_type": "REINDEX_SNAPSHOTS",
                    "pending_jobs": 1,
                    "processing_jobs": 0,
                    "failed_jobs": 2,
                    "oldest_pending_created_at": now - timedelta(seconds=10),
                },
            ]

    class _FakeSession:
        async def execute(self, _stmt):
            return _FakeResult()

        def begin(self):
            return _FakeBegin()

    async def _mock_get_async_db_session():
        yield _FakeSession()

    monkeypatch.setattr(service_module, "get_async_db_session", _mock_get_async_db_session)

    response = await service.get_reprocessing_queue_health()
    assert response.total_pending_jobs == 4
    assert response.total_processing_jobs == 1
    assert response.total_failed_jobs == 2
    assert response.queues[0].job_type == "RESET_WATERMARKS"
    assert response.queues[0].oldest_pending_age_seconds > 0
