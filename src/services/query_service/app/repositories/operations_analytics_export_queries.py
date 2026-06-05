from __future__ import annotations

from datetime import datetime

from portfolio_common.database_models import AnalyticsExportJob
from sqlalchemy import and_, case


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
    portfolio_id: str,
    status: str | None = None,
    job_id: str | None = None,
    request_fingerprint: str | None = None,
    as_of: datetime | None = None,
):
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
