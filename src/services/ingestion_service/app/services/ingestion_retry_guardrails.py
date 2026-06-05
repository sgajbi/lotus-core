from __future__ import annotations

from datetime import datetime


def assert_replay_guardrails(
    *,
    mode: str,
    replay_window_start: datetime | None,
    replay_window_end: datetime | None,
    submitted_at: datetime,
    replay_record_count: int,
    backlog_jobs: int,
    now: datetime,
    max_records_per_request: int,
    max_backlog_jobs: int,
) -> None:
    if mode == "paused":
        raise PermissionError("Retries are blocked while ingestion is paused.")
    if replay_window_start and now < replay_window_start:
        raise PermissionError("Current time is before configured replay window.")
    if replay_window_end and now > replay_window_end:
        raise PermissionError("Current time is after configured replay window.")
    if now < submitted_at:
        raise PermissionError("Retry blocked: job submission timestamp is in the future.")
    if replay_record_count > max_records_per_request:
        raise PermissionError(
            "Retry blocked: requested replay record count exceeds configured limit. "
            f"requested_records={replay_record_count}, "
            f"max_records={max_records_per_request}."
        )
    if backlog_jobs >= max_backlog_jobs:
        raise PermissionError(
            "Retry blocked: ingestion backlog exceeds configured replay safety threshold. "
            f"backlog_jobs={backlog_jobs}, max_backlog_jobs={max_backlog_jobs}."
        )
