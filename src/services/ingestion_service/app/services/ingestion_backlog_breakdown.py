from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import and_, case, func, select

from ..DTOs.ingestion_job_dto import (
    IngestionBacklogBreakdownItemResponse,
    IngestionBacklogBreakdownResponse,
)

SessionFactory = Callable[[], AsyncIterator[object]]


async def load_backlog_breakdown_response(
    *,
    lookback_minutes: int,
    limit: int,
    session_factory: SessionFactory,
    now: datetime | None = None,
) -> IngestionBacklogBreakdownResponse:
    now_utc = now or datetime.now(UTC)
    since = now_utc - timedelta(minutes=lookback_minutes)
    async for db in session_factory():
        total_backlog_jobs = int(
            (
                await db.scalar(
                    select(func.count(DBIngestionJob.id)).where(
                        and_(
                            DBIngestionJob.submitted_at >= since,
                            DBIngestionJob.submitted_at <= now_utc,
                            DBIngestionJob.status.in_(["accepted", "queued"]),
                        )
                    )
                )
            )
            or 0
        )
        rows = await db.execute(
            select(
                DBIngestionJob.endpoint,
                DBIngestionJob.entity_type,
                func.count(DBIngestionJob.id).label("total_jobs"),
                func.sum(case((DBIngestionJob.status == "accepted", 1), else_=0)).label(
                    "accepted_jobs"
                ),
                func.sum(case((DBIngestionJob.status == "queued", 1), else_=0)).label(
                    "queued_jobs"
                ),
                func.sum(case((DBIngestionJob.status == "failed", 1), else_=0)).label(
                    "failed_jobs"
                ),
                func.min(
                    case(
                        (
                            DBIngestionJob.status.in_(["accepted", "queued"]),
                            DBIngestionJob.submitted_at,
                        ),
                        else_=None,
                    )
                ).label("oldest_backlog_submitted_at"),
            )
            .where(DBIngestionJob.submitted_at >= since)
            .where(DBIngestionJob.submitted_at <= now_utc)
            .group_by(DBIngestionJob.endpoint, DBIngestionJob.entity_type)
        )

        return build_backlog_breakdown_response(
            lookback_minutes=lookback_minutes,
            total_backlog_jobs=total_backlog_jobs,
            grouped_rows=list(rows.all()),
            now=now_utc,
            limit=limit,
        )

    return empty_backlog_breakdown_response(lookback_minutes=lookback_minutes)


def build_backlog_breakdown_response(
    *,
    lookback_minutes: int,
    total_backlog_jobs: int,
    grouped_rows: list[Any],
    now: datetime,
    limit: int,
) -> IngestionBacklogBreakdownResponse:
    items = [backlog_breakdown_item_from_row(row=row, now=now) for row in grouped_rows]
    ordered_items = sorted(
        items,
        key=lambda item: (item.backlog_jobs, item.oldest_backlog_age_seconds),
        reverse=True,
    )[:limit]
    largest_group_backlog_jobs = int(ordered_items[0].backlog_jobs if ordered_items else 0)
    return IngestionBacklogBreakdownResponse(
        lookback_minutes=lookback_minutes,
        total_backlog_jobs=total_backlog_jobs,
        largest_group_backlog_jobs=largest_group_backlog_jobs,
        largest_group_backlog_share=_backlog_share(
            numerator=largest_group_backlog_jobs,
            denominator=total_backlog_jobs,
        ),
        top_3_backlog_share=_backlog_share(
            numerator=sum(item.backlog_jobs for item in ordered_items[:3]),
            denominator=total_backlog_jobs,
        ),
        groups=ordered_items,
    )


def backlog_breakdown_item_from_row(
    *,
    row: Any,
    now: datetime,
) -> IngestionBacklogBreakdownItemResponse:
    (
        endpoint,
        entity_type,
        total_jobs_raw,
        accepted_jobs_raw,
        queued_jobs_raw,
        failed_jobs_raw,
        oldest_backlog_submitted_at,
    ) = row
    accepted_jobs = _int_or_zero(accepted_jobs_raw)
    queued_jobs = _int_or_zero(queued_jobs_raw)
    failed_jobs = _int_or_zero(failed_jobs_raw)
    total_jobs = _int_or_zero(total_jobs_raw)
    return IngestionBacklogBreakdownItemResponse(
        endpoint=endpoint,
        entity_type=entity_type,
        total_jobs=total_jobs,
        accepted_jobs=accepted_jobs,
        queued_jobs=queued_jobs,
        failed_jobs=failed_jobs,
        backlog_jobs=accepted_jobs + queued_jobs,
        oldest_backlog_submitted_at=oldest_backlog_submitted_at,
        oldest_backlog_age_seconds=_backlog_age_seconds(
            oldest_submitted_at=oldest_backlog_submitted_at,
            now=now,
        ),
        failure_rate=_failure_rate(failed_jobs=failed_jobs, total_jobs=total_jobs),
    )


def empty_backlog_breakdown_response(
    *,
    lookback_minutes: int,
) -> IngestionBacklogBreakdownResponse:
    return IngestionBacklogBreakdownResponse(
        lookback_minutes=lookback_minutes,
        total_backlog_jobs=0,
        largest_group_backlog_jobs=0,
        largest_group_backlog_share=Decimal("0"),
        top_3_backlog_share=Decimal("0"),
        groups=[],
    )


def _backlog_share(
    *,
    numerator: int,
    denominator: int,
) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator)


def _failure_rate(
    *,
    failed_jobs: int,
    total_jobs: int,
) -> Decimal:
    if total_jobs <= 0:
        return Decimal("0")
    return Decimal(failed_jobs) / Decimal(total_jobs)


def _int_or_zero(value: Any) -> int:
    return int(value or 0)


def _backlog_age_seconds(
    *,
    oldest_submitted_at: datetime | None,
    now: datetime,
) -> float:
    if oldest_submitted_at is None:
        return 0.0
    return max(0.0, (now - oldest_submitted_at).total_seconds())
