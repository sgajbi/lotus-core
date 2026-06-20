from __future__ import annotations

from datetime import UTC, datetime

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import func, select

from .ingestion_retry_guardrails import assert_replay_guardrails


async def count_backlog_jobs(*, session_factory) -> int:
    async for db in session_factory():
        backlog = int(
            (
                await db.scalar(
                    select(func.count(DBIngestionJob.id)).where(
                        DBIngestionJob.status.in_(("accepted", "queued"))
                    )
                )
            )
            or 0
        )
        return backlog
    return 0


async def assert_retry_allowed_for_record_count(
    *,
    submitted_at: datetime,
    replay_record_count: int,
    ops_mode_loader,
    backlog_counter,
    max_records_per_request: int,
    max_backlog_jobs: int,
) -> None:
    mode = await ops_mode_loader()
    backlog_jobs = await backlog_counter()
    assert_replay_guardrails(
        mode=mode.mode,
        replay_window_start=mode.replay_window_start,
        replay_window_end=mode.replay_window_end,
        submitted_at=submitted_at,
        replay_record_count=replay_record_count,
        backlog_jobs=backlog_jobs,
        now=datetime.now(UTC),
        max_records_per_request=max_records_per_request,
        max_backlog_jobs=max_backlog_jobs,
    )


async def assert_reprocessing_publish_allowed_for_count(
    *,
    record_count: int,
    retry_permission_checker,
) -> None:
    await retry_permission_checker(
        submitted_at=datetime.now(UTC),
        replay_record_count=max(1, int(record_count)),
    )
