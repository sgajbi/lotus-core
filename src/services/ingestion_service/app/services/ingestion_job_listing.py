from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import desc, select

from ..DTOs.ingestion_job_dto import IngestionJobStatus


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
