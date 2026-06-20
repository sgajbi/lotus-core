from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import desc, select

from ..DTOs.ingestion_job_dto import IngestionJobResponse, IngestionJobStatus
from .ingestion_job_lifecycle import to_job_response


@dataclass(frozen=True, slots=True)
class IngestionJobListFilters:
    status: IngestionJobStatus | None = None
    entity_type: str | None = None
    submitted_from: datetime | None = None
    submitted_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class IngestionJobListPage:
    rows: list[Any]
    next_cursor: str | None


def build_ingestion_job_list_statement(
    *,
    filters: IngestionJobListFilters,
    cursor_row: Any | None,
    limit: int,
) -> Any:
    stmt = select(DBIngestionJob)
    if filters.status is not None:
        stmt = stmt.where(DBIngestionJob.status == filters.status)
    if filters.entity_type is not None:
        stmt = stmt.where(DBIngestionJob.entity_type == filters.entity_type)
    if filters.submitted_from is not None:
        stmt = stmt.where(DBIngestionJob.submitted_at >= filters.submitted_from)
    if filters.submitted_to is not None:
        stmt = stmt.where(DBIngestionJob.submitted_at <= filters.submitted_to)
    if cursor_row is not None:
        stmt = stmt.where(DBIngestionJob.id < cursor_row.id)
    return stmt.order_by(desc(DBIngestionJob.id)).limit(limit + 1)


def build_cursor_lookup_statement(*, cursor: str) -> Any:
    return select(DBIngestionJob).where(DBIngestionJob.job_id == cursor).limit(1)


def ingestion_job_list_page(
    *,
    rows: list[Any],
    limit: int,
) -> IngestionJobListPage:
    page_rows = rows[:limit]
    return IngestionJobListPage(
        rows=page_rows,
        next_cursor=page_rows[-1].job_id if len(rows) > limit and page_rows else None,
    )


async def load_job_list_response(
    *,
    filters: IngestionJobListFilters,
    cursor: str | None,
    limit: int,
    session_factory,
) -> tuple[list[IngestionJobResponse], str | None]:
    async for db in session_factory():
        cursor_row = None
        if cursor is not None:
            cursor_row = await db.scalar(build_cursor_lookup_statement(cursor=cursor))
        stmt = build_ingestion_job_list_statement(
            filters=filters,
            cursor_row=cursor_row,
            limit=limit,
        )
        rows = list((await db.scalars(stmt)).all())
        page = ingestion_job_list_page(rows=rows, limit=limit)
        return ([to_job_response(row) for row in page.rows], page.next_cursor)
    return ([], None)
