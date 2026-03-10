from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class RepoSnapshot:
    branch: str
    head_sha: str
    dirty: bool
    dirty_files: int
    captured_at: str


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def capture_snapshot(repo: Path) -> RepoSnapshot:
    branch = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    head_sha = _run_git(repo, "rev-parse", "HEAD")
    status_output = _run_git(repo, "status", "--porcelain")
    dirty_lines = [line for line in status_output.splitlines() if line.strip()]
    return RepoSnapshot(
        branch=branch,
        head_sha=head_sha,
        dirty=bool(dirty_lines),
        dirty_files=len(dirty_lines),
        captured_at=datetime.now(UTC).isoformat(),
    )


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {}
    return json.loads(state_file.read_text(encoding="utf-8"))


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def idle_changed(previous: dict, current: RepoSnapshot) -> bool:
    if not previous:
        return True
    return (
        previous.get("branch") != current.branch
        or previous.get("head_sha") != current.head_sha
        or previous.get("dirty") != current.dirty
        or previous.get("dirty_files") != current.dirty_files
    )


def update_state(previous: dict, current: RepoSnapshot) -> dict:
    last_change_at = (
        current.captured_at
        if idle_changed(previous, current)
        else previous["last_change_at"]
    )
    first_seen_at = previous.get("first_seen_at", current.captured_at)
    return {
        **asdict(current),
        "first_seen_at": first_seen_at,
        "last_change_at": last_change_at,
    }


def idle_minutes(state: dict, now: datetime) -> float:
    last_change = datetime.fromisoformat(state["last_change_at"])
    return (now - last_change).total_seconds() / 60.0


def emit_status(state: dict, threshold_minutes: float) -> str:
    minutes = idle_minutes(state, datetime.now(UTC))
    status = (
        f"[heartbeat] branch={state['branch']} sha={state['head_sha'][:8]} "
        f"dirty={state['dirty']} dirty_files={state['dirty_files']} idle_minutes={minutes:.1f}"
    )
    if minutes >= threshold_minutes:
        return f"{status}\ngo"
    return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minimal local heartbeat that prints 'go' when repo activity is idle."
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root to monitor.")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("output/agent-heartbeat.json"),
        help="JSON state file used to persist last observed change.",
    )
    parser.add_argument(
        "--idle-minutes",
        type=float,
        default=5.0,
        help="Minutes of no git-state change before emitting 'go'.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=60.0,
        help="Polling interval when --watch is enabled.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously monitor until interrupted.",
    )
    return parser.parse_args()


def run_once(repo: Path, state_file: Path, threshold_minutes: float) -> int:
    previous = load_state(state_file)
    current = capture_snapshot(repo)
    state = update_state(previous, current)
    save_state(state_file, state)
    print(emit_status(state, threshold_minutes))
    return 0


def run_watch(repo: Path, state_file: Path, threshold_minutes: float, poll_seconds: float) -> int:
    while True:
        run_once(repo, state_file, threshold_minutes)
        time.sleep(poll_seconds)


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    state_file = args.state_file if args.state_file.is_absolute() else (repo / args.state_file)

    try:
        if args.watch:
            return run_watch(repo, state_file, args.idle_minutes, args.poll_seconds)
        return run_once(repo, state_file, args.idle_minutes)
    except KeyboardInterrupt:
        return 130
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
