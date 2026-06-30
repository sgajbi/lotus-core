from __future__ import annotations

from datetime import UTC
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.services import ingestion_replay_audits as module

pytestmark = pytest.mark.asyncio


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


async def test_find_successful_replay_audit_by_fingerprint_returns_latest_identity():
    class _FakeSession:
        async def scalar(self, _stmt):
            return SimpleNamespace(
                replay_id="replay_123",
                replay_status="replayed_bookkeeping_failed",
            )

    response = await module.find_successful_replay_audit_by_fingerprint_response(
        replay_fingerprint="fp_123",
        recovery_path="consumer_dlq_replay",
        session_factory=lambda: _SingleSessionAsyncIterable(_FakeSession()),
    )

    assert response == {
        "replay_id": "replay_123",
        "replay_status": "replayed_bookkeeping_failed",
    }


async def test_find_successful_replay_audit_by_fingerprint_handles_missing_match():
    class _FakeSession:
        async def scalar(self, _stmt):
            return None

    response = await module.find_successful_replay_audit_by_fingerprint_response(
        replay_fingerprint="fp_missing",
        recovery_path=None,
        session_factory=lambda: _SingleSessionAsyncIterable(_FakeSession()),
    )

    assert response is None


async def test_record_consumer_dlq_replay_audit_persists_row_and_metrics(
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

    session = _FakeSession()
    audit_counter = _FakeCounterVec()
    duplicate_counter = _FakeCounterVec()
    failure_counter = _FakeCounterVec()
    monkeypatch.setattr(module, "INGESTION_REPLAY_AUDIT_TOTAL", audit_counter)
    monkeypatch.setattr(module, "INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL", duplicate_counter)
    monkeypatch.setattr(module, "INGESTION_REPLAY_FAILURE_TOTAL", failure_counter)

    replay_id = await module.record_consumer_dlq_replay_audit_response(
        recovery_path="consumer_dlq_replay",
        event_id="event_123",
        replay_fingerprint="fp_123",
        correlation_id="corr-123",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
        job_id="job_123",
        endpoint="/ingest/transactions",
        replay_status="replayed_bookkeeping_failed",
        dry_run=False,
        replay_reason="publish succeeded but bookkeeping failed",
        requested_by="ops-token",
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    assert replay_id.startswith("replay_")
    assert session.added[0].replay_id == replay_id
    assert session.added[0].completed_at.tzinfo is UTC
    assert audit_counter.labels(
        recovery_path="consumer_dlq_replay",
        replay_status="replayed_bookkeeping_failed",
    ).calls == [1]
    assert failure_counter.labels(
        recovery_path="consumer_dlq_replay",
        replay_status="replayed_bookkeeping_failed",
    ).calls == [1]
    assert duplicate_counter.handles == {}


async def test_record_consumer_dlq_replay_audit_persists_missing_correlation_diagnostics():
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

    session = _FakeSession()

    await module.record_consumer_dlq_replay_audit_response(
        recovery_path="consumer_dlq_replay",
        event_id="event_456",
        replay_fingerprint="fp_456",
        correlation_id=None,
        job_id=None,
        endpoint=None,
        replay_status="not_replayable",
        dry_run=True,
        replay_reason="missing correlation",
        requested_by="ops-token",
        session_factory=lambda: _SingleSessionAsyncIterable(session),
        correlation_missing_reason="message_correlation_id_absent",
        alternate_lookup_key="consumer_dlq|topic=transactions.raw.received|event=event_456",
    )

    assert session.added[0].correlation_id is None
    assert session.added[0].correlation_missing_reason == "message_correlation_id_absent"
    assert (
        session.added[0].alternate_lookup_key
        == "consumer_dlq|topic=transactions.raw.received|event=event_456"
    )


async def test_record_consumer_dlq_replay_audit_raises_typed_error_when_no_session():
    async def _empty_session_factory():
        if False:
            yield None

    with pytest.raises(module.InfrastructureAuditWriteFailed) as exc_info:
        await module.record_consumer_dlq_replay_audit_response(
            recovery_path="consumer_dlq_replay",
            event_id="event_123",
            replay_fingerprint="fp_123",
            correlation_id="corr-123",
            job_id="job_123",
            endpoint="/ingest/transactions",
            replay_status="failed",
            dry_run=False,
            replay_reason="no session",
            requested_by="ops-token",
            session_factory=_empty_session_factory,
        )

    assert str(exc_info.value) == "Unable to record consumer DLQ replay audit."
    assert exc_info.value.reason_code == "audit_session_unavailable"


async def test_record_consumer_dlq_replay_audit_wraps_persistence_failure():
    class _FailingBegin:
        async def __aenter__(self):
            raise ConnectionError("database unavailable")

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FailingSession:
        def begin(self):
            return _FailingBegin()

    with pytest.raises(module.InfrastructureAuditWriteFailed) as exc_info:
        await module.record_consumer_dlq_replay_audit_response(
            recovery_path="consumer_dlq_replay",
            event_id="event_123",
            replay_fingerprint="fp_123",
            correlation_id="corr-123",
            job_id="job_123",
            endpoint="/ingest/transactions",
            replay_status="failed",
            dry_run=False,
            replay_reason="db down",
            requested_by="ops-token",
            session_factory=lambda: _SingleSessionAsyncIterable(_FailingSession()),
        )

    assert str(exc_info.value) == "Unable to record consumer DLQ replay audit."
    assert exc_info.value.reason_code == "audit_persistence_failed"
    assert isinstance(exc_info.value.__cause__, ConnectionError)
