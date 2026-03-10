from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.agent_heartbeat import (
    RepoSnapshot,
    emit_status,
    idle_changed,
    idle_minutes,
    update_state,
)


def test_idle_changed_detects_head_change() -> None:
    previous = {
        "branch": "feat/test",
        "head_sha": "abc",
        "dirty": False,
        "dirty_files": 0,
        "first_seen_at": "2026-03-10T10:00:00+00:00",
        "last_change_at": "2026-03-10T10:00:00+00:00",
    }
    current = RepoSnapshot(
        branch="feat/test",
        head_sha="def",
        dirty=False,
        dirty_files=0,
        captured_at="2026-03-10T10:05:00+00:00",
    )
    assert idle_changed(previous, current) is True


def test_update_state_preserves_last_change_when_idle() -> None:
    previous = {
        "branch": "feat/test",
        "head_sha": "abc",
        "dirty": False,
        "dirty_files": 0,
        "first_seen_at": "2026-03-10T10:00:00+00:00",
        "last_change_at": "2026-03-10T10:01:00+00:00",
    }
    current = RepoSnapshot(
        branch="feat/test",
        head_sha="abc",
        dirty=False,
        dirty_files=0,
        captured_at="2026-03-10T10:05:00+00:00",
    )
    state = update_state(previous, current)
    assert state["last_change_at"] == "2026-03-10T10:01:00+00:00"
    assert state["first_seen_at"] == "2026-03-10T10:00:00+00:00"


def test_idle_minutes_computes_elapsed_time() -> None:
    now = datetime.now(UTC)
    state = {"last_change_at": (now - timedelta(minutes=7)).isoformat()}
    assert 6.9 <= idle_minutes(state, now) <= 7.1


def test_emit_status_includes_go_when_threshold_breached() -> None:
    state = {
        "branch": "feat/test",
        "head_sha": "abcdef123456",
        "dirty": False,
        "dirty_files": 0,
        "last_change_at": (datetime.now(UTC) - timedelta(minutes=6)).isoformat(),
    }
    message = emit_status(state, threshold_minutes=5.0)
    assert "go" in message.splitlines()
