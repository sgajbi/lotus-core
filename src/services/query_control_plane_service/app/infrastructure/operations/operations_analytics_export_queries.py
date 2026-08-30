"""SQL query policies for analytics export support jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from portfolio_common.database_models import AnalyticsExportJob, Portfolio
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def analytics_export_portfolio_exists(
    db: AsyncSession, *, tenant_id: str, portfolio_id: str
) -> bool:
    stmt = (
        select(Portfolio.portfolio_id)
        .where(
            Portfolio.tenant_id == tenant_id,
            Portfolio.portfolio_id == portfolio_id,
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def count_analytics_export_jobs(
    db: AsyncSession,
    *,
    tenant_id: str,
    portfolio_id: str,
    status: str | None,
    job_id: str | None,
    request_fingerprint: str | None,
    as_of: datetime | None,
) -> int:
    stmt = apply_analytics_export_job_scope(
        select(func.count()).select_from(AnalyticsExportJob),
        tenant_id=tenant_id,
        portfolio_id=portfolio_id,
        status=status,
        job_id=job_id,
        request_fingerprint=request_fingerprint,
        as_of=as_of,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def list_analytics_export_jobs(
    db: AsyncSession,
    *,
    tenant_id: str,
    portfolio_id: str,
    skip: int,
    limit: int,
    status: str | None,
    job_id: str | None,
    request_fingerprint: str | None,
    stale_minutes: int,
    reference_now: datetime | None,
    as_of: datetime | None,
) -> list[AnalyticsExportJob]:
    reference_now = reference_now or datetime.now(timezone.utc)
    stale_threshold = reference_now - timedelta(minutes=stale_minutes)
    stmt = apply_analytics_export_job_scope(
        select(AnalyticsExportJob),
        tenant_id=tenant_id,
        portfolio_id=portfolio_id,
        status=status,
        job_id=job_id,
        request_fingerprint=request_fingerprint,
        as_of=as_of,
    )
    stmt = (
        stmt.order_by(
            analytics_export_job_priority(
                AnalyticsExportJob.status,
                AnalyticsExportJob.updated_at,
                stale_threshold,
            ).asc(),
            AnalyticsExportJob.created_at.asc(),
            AnalyticsExportJob.id.asc(),
        )
        .offset(skip)
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


def analytics_export_status_filter(status_column, status: str):
    return status_column == status.strip().lower()


def analytics_export_job_priority(status_column, updated_at_column, stale_threshold: datetime):
    governed_status = status_column
    return case(
        (governed_status == "failed", 0),
        (
            and_(governed_status == "running", updated_at_column < stale_threshold),
            1,
        ),
        (governed_status == "running", 2),
        (governed_status == "accepted", 3),
        else_=9,
    )


def apply_analytics_export_job_scope(
    stmt,
    *,
    tenant_id: str,
    portfolio_id: str,
    status: str | None = None,
    job_id: str | None = None,
    request_fingerprint: str | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(AnalyticsExportJob.tenant_id == tenant_id)
    return apply_analytics_export_job_portfolio_scope(
        stmt,
        portfolio_id=portfolio_id,
        status=status,
        job_id=job_id,
        request_fingerprint=request_fingerprint,
        as_of=as_of,
    )


def apply_analytics_export_job_portfolio_scope(
    stmt,
    *,
    portfolio_id: str,
    status: str | None = None,
    job_id: str | None = None,
    request_fingerprint: str | None = None,
    as_of: datetime | None = None,
):
    """Apply legacy portfolio scope pending the broader #798 operations-support slice."""

    stmt = stmt.where(AnalyticsExportJob.portfolio_id == portfolio_id)
    if as_of is not None:
        stmt = stmt.where(AnalyticsExportJob.updated_at <= as_of)
    if status:
        stmt = stmt.where(analytics_export_status_filter(AnalyticsExportJob.status, status))
    if job_id:
        stmt = stmt.where(AnalyticsExportJob.job_id == job_id)
    if request_fingerprint:
        stmt = stmt.where(AnalyticsExportJob.request_fingerprint == request_fingerprint)
    return stmt
