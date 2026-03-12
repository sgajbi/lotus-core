from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine

SNAPSHOT_QUERIES: dict[str, tuple[str, str]] = {
    "outbox_pending": ("outbox_events", "status = 'PENDING'"),
    "ingestion_backlog": (
        "ingestion_jobs",
        "(status = 'accepted') OR (status = 'queued' AND completed_at IS NULL)",
    ),
    "aggregation_jobs_active": (
        "portfolio_aggregation_jobs",
        "status IN ('PENDING', 'PROCESSING')",
    ),
    "valuation_jobs_active": (
        "portfolio_valuation_jobs",
        "status IN ('PENDING', 'PROCESSING')",
    ),
    "reprocessing_jobs_active": ("reprocessing_jobs", "status IN ('PENDING', 'PROCESSING')"),
    "pipeline_stage_pending": ("pipeline_stage_state", "status = 'PENDING'"),
    "reconciliation_runs_active": ("financial_reconciliation_runs", "status = 'RUNNING'"),
    "position_state_reprocessing": ("position_state", "status = 'REPROCESSING'"),
    "instrument_reprocessing_active": ("instrument_reprocessing_state", "TRUE"),
}

BLOCKING_ACTIVITY_KEYS = frozenset(
    {
        "outbox_pending",
        "ingestion_backlog",
        "valuation_jobs_active",
        "reprocessing_jobs_active",
        "reconciliation_runs_active",
    }
)

ACTIVITY_TIMESTAMP_CANDIDATES = ("updated_at", "created_at")


def read_pipeline_activity_snapshot(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        existing_tables = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).fetchall()
        }
        snapshot: dict[str, int] = {}
        for key, (table_name, predicate) in SNAPSHOT_QUERIES.items():
            if table_name not in existing_tables:
                snapshot[key] = 0
                continue
            result = connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE {predicate}")
            ).scalar()
            snapshot[key] = int(result or 0)
        return snapshot


def read_pipeline_last_activity_at(engine: Engine) -> datetime | None:
    with engine.connect() as connection:
        existing_tables = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).fetchall()
        }
        timestamp_columns = {
            (row[0], row[1])
            for row in connection.execute(
                text(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND column_name IN ('updated_at', 'created_at')
                    """
                )
            ).fetchall()
        }

        timestamp_selects: list[str] = []
        blocking_tables = {
            table_name
            for key, (table_name, _predicate) in SNAPSHOT_QUERIES.items()
            if key in BLOCKING_ACTIVITY_KEYS
        }
        for table_name in blocking_tables:
            if table_name not in existing_tables:
                continue
            for column_name in ACTIVITY_TIMESTAMP_CANDIDATES:
                if (table_name, column_name) in timestamp_columns:
                    timestamp_selects.append(
                        f"SELECT MAX({column_name}) AS ts FROM {table_name}"
                    )
                    break

        if not timestamp_selects:
            return None

        union_sql = " UNION ALL ".join(timestamp_selects)
        result = connection.execute(text(f"SELECT MAX(ts) FROM ({union_sql}) AS activity_ts"))
        last_activity_at = result.scalar()
        if last_activity_at is None:
            return None
        if last_activity_at.tzinfo is None:
            return last_activity_at.replace(tzinfo=timezone.utc)
        return last_activity_at.astimezone(timezone.utc)


def is_pipeline_quiescent(snapshot: dict[str, int]) -> bool:
    return all(snapshot.get(key, 0) == 0 for key in BLOCKING_ACTIVITY_KEYS)


def format_pipeline_activity_snapshot(snapshot: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(snapshot.items()))


def wait_for_pipeline_quiescence(
    *,
    timeout_seconds: int = 180,
    poll_seconds: int = 2,
    stable_cycles: int = 3,
    snapshot_reader: Callable[[], dict[str, int]],
    quiet_seconds: int = 0,
    last_activity_reader: Callable[[], datetime | None] | None = None,
) -> dict[str, int]:
    deadline = time.time() + timeout_seconds
    last_snapshot: dict[str, int] | None = None
    stable_hits = 0

    while time.time() < deadline:
        snapshot = snapshot_reader()
        if is_pipeline_quiescent(snapshot):
            stable_hits = stable_hits + 1 if snapshot == last_snapshot else 1
            if stable_hits >= stable_cycles:
                if quiet_seconds <= 0 or last_activity_reader is None:
                    return snapshot
                last_activity_at = last_activity_reader()
                if last_activity_at is None:
                    return snapshot
                quiet_age_seconds = max(
                    0.0,
                    (datetime.now(timezone.utc) - last_activity_at).total_seconds(),
                )
                if quiet_age_seconds >= quiet_seconds:
                    return snapshot
        else:
            stable_hits = 0

        last_snapshot = snapshot
        time.sleep(poll_seconds)

    raise TimeoutError(
        "Pipeline did not reach a quiescent state within "
        f"{timeout_seconds}s. Last snapshot: "
        f"{format_pipeline_activity_snapshot(last_snapshot or {})}"
    )
