import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.services.ingestion_ops_mode import (
    assert_ingestion_writable_mode,
    load_ops_mode_response,
    to_ops_mode_response,
    update_ops_mode_response,
)

pytestmark = pytest.mark.asyncio


class _FakeBegin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeSession:
    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.flush_count = 0

    async def scalar(self, _stmt):
        return self.row

    def add(self, row):
        self.added.append(row)
        self.row = row

    async def flush(self):
        self.flush_count += 1
        if getattr(self.row, "updated_at", None) is None:
            self.row.updated_at = datetime(2026, 6, 17, 0, 0, tzinfo=UTC)

    def begin(self):
        return _FakeBegin()


def _session_factory(session):
    async def sessions():
        yield session  # This provider borrows the session; it never closes it.

    return sessions


class _FakeGauge:
    def __init__(self):
        self.values: list[int] = []

    def set(self, value: int) -> None:
        self.values.append(value)


async def test_to_ops_mode_response_preserves_control_fields() -> None:
    now = datetime(2026, 6, 17, 1, 2, 3, tzinfo=UTC)
    row = SimpleNamespace(
        mode="drain",
        replay_window_start=now,
        replay_window_end=now,
        updated_by="ops-user",
        updated_at=now,
    )

    response = to_ops_mode_response(row)

    assert response.mode == "drain"
    assert response.replay_window_start == now
    assert response.replay_window_end == now
    assert response.updated_by == "ops-user"
    assert response.updated_at == now


async def test_load_ops_mode_response_bootstraps_normal_mode_when_missing() -> None:
    session = _FakeSession()

    response = await load_ops_mode_response(session_factory=_session_factory(session))

    assert response.mode == "normal"
    assert response.updated_by == "system_bootstrap"
    assert session.flush_count == 1
    assert len(session.added) == 1


async def test_update_ops_mode_response_updates_existing_control_row() -> None:
    existing = SimpleNamespace(
        mode="normal",
        replay_window_start=None,
        replay_window_end=None,
        updated_by="system_bootstrap",
        updated_at=None,
    )
    session = _FakeSession(existing)
    window_start = datetime(2026, 6, 17, 2, 0, tzinfo=UTC)
    window_end = datetime(2026, 6, 17, 3, 0, tzinfo=UTC)

    response = await update_ops_mode_response(
        mode="paused",
        replay_window_start=window_start,
        replay_window_end=window_end,
        updated_by="ops-user",
        session_factory=_session_factory(session),
    )

    assert response.mode == "paused"
    assert response.replay_window_start == window_start
    assert response.replay_window_end == window_end
    assert response.updated_by == "ops-user"
    assert response.updated_at is not None
    assert session.added == []


async def test_assert_ingestion_writable_mode_records_normal_mode_metric() -> None:
    gauge = _FakeGauge()

    async def _load_mode():
        return SimpleNamespace(mode="normal")

    await assert_ingestion_writable_mode(
        ops_mode_loader=_load_mode,
        mode_state_metric=gauge,
    )

    assert gauge.values == [0]


async def test_assert_ingestion_writable_mode_blocks_paused_mode() -> None:
    gauge = _FakeGauge()

    async def _load_mode():
        return SimpleNamespace(mode="paused")

    with pytest.raises(PermissionError, match="currently in 'paused' mode"):
        await assert_ingestion_writable_mode(
            ops_mode_loader=_load_mode,
            mode_state_metric=gauge,
        )

    assert gauge.values == [1]


async def _invoke_mode_operation(operation, session_factory, mode="normal"):
    if operation == "read":
        return await load_ops_mode_response(session_factory=session_factory)
    return await update_ops_mode_response(
        mode=mode,
        replay_window_start=None,
        replay_window_end=None,
        updated_by="ops-user",
        session_factory=session_factory,
    )


@pytest.mark.parametrize("operation", ["read", "update"])
@pytest.mark.parametrize("mode", ["normal", "paused", "drain"])
async def test_mode_operation_awaits_provider_close_before_return(operation, mode):
    session = _FakeSession(
        SimpleNamespace(
            mode=mode,
            replay_window_start=None,
            replay_window_end=None,
            updated_by="ops-user",
            updated_at=datetime(2026, 6, 17, tzinfo=UTC),
        )
    )
    closing, release = asyncio.Event(), asyncio.Event()
    closed = []

    async def sessions():
        try:
            yield session
        finally:
            closing.set()
            await release.wait()
            closed.append(session)

    task = asyncio.create_task(_invoke_mode_operation(operation, sessions, mode))
    try:
        await asyncio.wait_for(closing.wait(), timeout=2)
        assert not task.done(), "Operation returned before awaited provider closure"
    finally:
        release.set()
        response = await task
    assert response.mode == mode
    assert response.updated_by == "ops-user"
    assert closed == [session]


@pytest.mark.parametrize("operation", ["read", "update"])
@pytest.mark.parametrize("outcome", ["exception", "cancellation"])
async def test_mode_operation_closes_provider_before_propagating_failure(operation, outcome):
    entered, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    sentinel = RuntimeError("native-read-fault")
    closed = []

    class FaultSession(_FakeSession):
        async def scalar(self, statement):
            entered.set()
            if outcome == "exception":
                raise sentinel
            await asyncio.Event().wait()

    session = FaultSession()

    async def sessions():
        try:
            yield session
        finally:
            closing.set()
            await release.wait()
            closed.append(session)

    task = asyncio.create_task(_invoke_mode_operation(operation, sessions))
    await asyncio.wait_for(entered.wait(), timeout=2)
    if outcome == "cancellation":
        task.cancel()
    try:
        await asyncio.wait_for(closing.wait(), timeout=2)
        assert not task.done(), "Failure escaped before awaited provider closure"
    finally:
        release.set()
        expected = RuntimeError if outcome == "exception" else asyncio.CancelledError
        with pytest.raises(expected) as caught:
            await task
    if outcome == "exception":
        assert caught.value is sentinel
    assert closed == [session]
