from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.agent_orchestrator import (
    build_codex_command,
    build_runtime_heartbeat_state,
    decide_trigger,
    run_once,
)


def test_decide_trigger_for_new_idle_window() -> None:
    heartbeat = {
        "branch": "feat/test",
        "head_sha": "abcdef123456",
        "last_change_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    }
    runtime = build_runtime_heartbeat_state(heartbeat)
    decision = decide_trigger(runtime, {}, idle_threshold_minutes=5.0, min_reprompt_minutes=15.0)
    assert decision.should_trigger is True
    assert decision.reason == "new-idle-window"


def test_decide_trigger_respects_reprompt_window() -> None:
    now = datetime.now(UTC)
    change_at = (now - timedelta(minutes=20)).isoformat()
    heartbeat = {
        "branch": "feat/test",
        "head_sha": "abcdef123456",
        "last_change_at": change_at,
    }
    runtime = build_runtime_heartbeat_state(heartbeat)
    state = {
        "last_trigger_change_at": change_at,
        "last_trigger_at": (now - timedelta(minutes=5)).isoformat(),
    }
    decision = decide_trigger(runtime, state, idle_threshold_minutes=5.0, min_reprompt_minutes=15.0)
    assert decision.should_trigger is False
    assert decision.reason == "reprompt-window-active"


def test_build_codex_command_uses_exec_mode(tmp_path: Path) -> None:
    command = build_codex_command(
        codex_bin=Path("codex.exe"),
        repo=Path("C:/repo"),
        prompt="go",
        output_file=tmp_path / "last.txt",
    )
    assert command[:5] == ["codex.exe", "exec", "--cd", str(Path("C:/repo")), "--full-auto"]
    assert command[-1] == "go"


def test_run_once_dry_run_updates_state(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat.json"
    state_file = tmp_path / "orchestrator.json"
    output_file = tmp_path / "last.txt"
    heartbeat_file.write_text(
        json.dumps(
            {
                "branch": "feat/test",
                "head_sha": "abcdef123456",
                "last_change_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_once(
        repo=tmp_path,
        heartbeat_file=heartbeat_file,
        state_file=state_file,
        output_file=output_file,
        idle_minutes=5.0,
        min_reprompt_minutes=15.0,
        prompt="go",
        codex_bin=Path("codex.exe"),
        dry_run=True,
    )

    assert exit_code == 0
    saved = state_file.read_text(encoding="utf-8")
    assert "last_trigger_at" in saved
    assert "last_command" in saved
