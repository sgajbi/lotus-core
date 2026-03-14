from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

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


class _SingleSessionAsyncIterable:
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


class _FakeCounterHandle:
    def __init__(self):
        self.calls: list[int] = []

    def inc(self, count: int = 1):
        self.calls.append(count)


class _FakeCounterVec:
    def __init__(self):
        self.handles: dict[tuple[tuple[str, object], ...], _FakeCounterHandle] = {}

    def labels(self, **labels):
        key = tuple(sorted(labels.items()))
        return self.handles.setdefault(key, _FakeCounterHandle())


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

    with pytest.raises(
        PermissionError, match="requested replay record count exceeds configured limit"
    ):
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

    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        lambda: _SingleSessionAsyncIterable(_FakeSession()),
    )
    monkeypatch.setattr(service_module, "REPLAY_MAX_BACKLOG_JOBS", 5000)
    monkeypatch.setattr(service_module, "DLQ_BUDGET_EVENTS_PER_WINDOW", 10)

    result = await service.get_error_budget_status()
    assert result.failure_rate == Decimal("0.05")
    assert result.replay_backlog_pressure_ratio == Decimal("0.004")
    assert result.dlq_events_in_window == 4
    assert result.dlq_budget_events_per_window == 10
    assert result.dlq_pressure_ratio == Decimal("0.4")


async def test_get_slo_status_returns_safe_default_when_queries_unavailable(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    class _BrokenSession:
        async def execute(self, _stmt):
            raise SQLAlchemyError("relation missing")

        async def scalars(self, _stmt):
            raise SQLAlchemyError("relation missing")

    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        lambda: _SingleSessionAsyncIterable(_BrokenSession()),
    )

    result = await service.get_slo_status()

    assert result.total_jobs == 0
    assert result.failed_jobs == 0
    assert result.failure_rate == Decimal("0")
    assert result.breach_failure_rate is False
    assert result.breach_queue_latency is False
    assert result.breach_backlog_age is False


async def test_get_error_budget_status_returns_safe_default_when_queries_unavailable(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    class _BrokenSession:
        async def execute(self, _stmt):
            raise SQLAlchemyError("relation missing")

    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        lambda: _SingleSessionAsyncIterable(_BrokenSession()),
    )

    result = await service.get_error_budget_status(failure_rate_threshold=Decimal("0.03"))

    assert result.total_jobs == 0
    assert result.failed_jobs == 0
    assert result.failure_rate == Decimal("0")
    assert result.remaining_error_budget == Decimal("0.03")
    assert result.dlq_pressure_ratio == Decimal("0")
    assert result.breach_failure_rate is False
    assert result.breach_backlog_growth is False


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
    assert policy.reprocessing_worker_poll_interval_seconds >= 1
    assert policy.reprocessing_worker_batch_size >= 1
    assert policy.valuation_scheduler_poll_interval_seconds >= 1
    assert policy.valuation_scheduler_batch_size >= 1
    assert policy.valuation_scheduler_dispatch_rounds >= 1
    assert policy.dlq_budget_events_per_window >= 1
    assert set(policy.calculator_peak_lag_age_seconds.keys()) == {
        "position",
        "cost",
        "valuation",
        "cashflow",
        "timeseries",
    }
    assert policy.replay_isolation_mode in {"shared_workers", "dedicated_workers"}
    assert policy.partition_growth_strategy in {
        "scale_out_only",
        "pre_shard_large_portfolios",
    }


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


async def test_record_consumer_dlq_replay_audit_increments_duplicate_blocked_metric(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeBegin:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FakeSession:
        def __init__(self):
            self.added = []

        def add(self, row):
            self.added.append(row)

        def begin(self):
            return _FakeBegin()

    audit_counter = _FakeCounterVec()
    duplicate_counter = _FakeCounterVec()
    failure_counter = _FakeCounterVec()

    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        lambda: _SingleSessionAsyncIterable(_FakeSession()),
    )
    monkeypatch.setattr(service_module, "INGESTION_REPLAY_AUDIT_TOTAL", audit_counter)
    monkeypatch.setattr(
        service_module,
        "INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL",
        duplicate_counter,
    )
    monkeypatch.setattr(service_module, "INGESTION_REPLAY_FAILURE_TOTAL", failure_counter)

    replay_id = await service.record_consumer_dlq_replay_audit(
        recovery_path="ingestion_job_retry",
        event_id="job:job_123",
        replay_fingerprint="fp_123",
        correlation_id="corr-123",
        job_id="job_123",
        endpoint="/ingest/transactions",
        replay_status="duplicate_blocked",
        dry_run=False,
        replay_reason="duplicate",
        requested_by="ops-token",
    )

    assert replay_id.startswith("replay_")
    assert audit_counter.labels(
        recovery_path="ingestion_job_retry",
        replay_status="duplicate_blocked",
    ).calls == [1]
    assert duplicate_counter.labels(recovery_path="ingestion_job_retry").calls == [1]
    assert failure_counter.handles == {}


async def test_record_consumer_dlq_replay_audit_increments_failure_metric(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeBegin:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FakeSession:
        def add(self, _row):
            return None

        def begin(self):
            return _FakeBegin()

    audit_counter = _FakeCounterVec()
    duplicate_counter = _FakeCounterVec()
    failure_counter = _FakeCounterVec()

    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        lambda: _SingleSessionAsyncIterable(_FakeSession()),
    )
    monkeypatch.setattr(service_module, "INGESTION_REPLAY_AUDIT_TOTAL", audit_counter)
    monkeypatch.setattr(
        service_module,
        "INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL",
        duplicate_counter,
    )
    monkeypatch.setattr(service_module, "INGESTION_REPLAY_FAILURE_TOTAL", failure_counter)

    await service.record_consumer_dlq_replay_audit(
        recovery_path="consumer_dlq_replay",
        event_id="event_123",
        replay_fingerprint="fp_456",
        correlation_id="corr-456",
        job_id="job_456",
        endpoint="/ingest/transactions",
        replay_status="failed",
        dry_run=False,
        replay_reason="publish exploded",
        requested_by="ops-token",
    )

    assert audit_counter.labels(
        recovery_path="consumer_dlq_replay",
        replay_status="failed",
    ).calls == [1]
    assert failure_counter.labels(
        recovery_path="consumer_dlq_replay",
        replay_status="failed",
    ).calls == [1]
    assert duplicate_counter.handles == {}


async def test_record_consumer_dlq_replay_audit_increments_bookkeeping_failure_metric(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeBegin:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FakeSession:
        def add(self, _row):
            return None

        def begin(self):
            return _FakeBegin()

    audit_counter = _FakeCounterVec()
    duplicate_counter = _FakeCounterVec()
    failure_counter = _FakeCounterVec()

    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        lambda: _SingleSessionAsyncIterable(_FakeSession()),
    )
    monkeypatch.setattr(service_module, "INGESTION_REPLAY_AUDIT_TOTAL", audit_counter)
    monkeypatch.setattr(
        service_module,
        "INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL",
        duplicate_counter,
    )
    monkeypatch.setattr(service_module, "INGESTION_REPLAY_FAILURE_TOTAL", failure_counter)

    await service.record_consumer_dlq_replay_audit(
        recovery_path="consumer_dlq_replay",
        event_id="event_123",
        replay_fingerprint="fp_789",
        correlation_id="corr-789",
        job_id="job_789",
        endpoint="/ingest/transactions",
        replay_status="replayed_bookkeeping_failed",
        dry_run=False,
        replay_reason="publish succeeded but bookkeeping failed",
        requested_by="ops-token",
    )

    assert audit_counter.labels(
        recovery_path="consumer_dlq_replay",
        replay_status="replayed_bookkeeping_failed",
    ).calls == [1]
    assert failure_counter.labels(
        recovery_path="consumer_dlq_replay",
        replay_status="replayed_bookkeeping_failed",
    ).calls == [1]
    assert duplicate_counter.handles == {}
