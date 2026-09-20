"""Flush Integration Full test progress before a possible native process exit."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _record(event: str, nodeid: str, **details: Any) -> None:
    configured_path = os.getenv("LOTUS_INTEGRATION_ALL_PROGRESS_PATH")
    if not configured_path:
        return
    path = Path(configured_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event": event,
        "nodeid": nodeid,
        "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pid": os.getpid(),
        **details,
    }
    with path.open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(record, sort_keys=True) + "\n")


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int, str]) -> None:  # noqa: ARG001
    """Persist the running node before its setup or call can terminate pytest."""

    _record("start", nodeid)


def pytest_runtest_logreport(report: Any) -> None:
    """Persist each completed phase without relying on end-of-session JUnit."""

    _record(
        "phase",
        report.nodeid,
        phase=report.when,
        outcome=report.outcome,
        duration_seconds=report.duration,
    )
