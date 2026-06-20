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
    return lambda: _SingleSessionAsyncIterator(session)


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
