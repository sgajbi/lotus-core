from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select, true

from .identifier_normalization import normalize_security_id
from .operations_models import ExportJobHealthSummary, JobHealthSummary


def int_or_zero(value) -> int:
    return int(value) if value is not None else 0


def seconds_or_none(raw) -> float | None:
    if raw is None:
        return None
    return float(raw)


def support_job_health_aggregate(base_subq, open_date_column, stale_threshold, failed_since):
    open_statuses = ("PENDING", "PROCESSING")
    return (
        select(
            func.count().filter(base_subq.c.status.in_(open_statuses)).label("pending_jobs"),
            func.count().filter(base_subq.c.status == "PROCESSING").label("processing_jobs"),
            func.count()
            .filter(
                base_subq.c.status == "PROCESSING",
                base_subq.c.updated_at < stale_threshold,
            )
            .label("stale_processing_jobs"),
            func.count().filter(base_subq.c.status == "FAILED").label("failed_jobs"),
            func.count()
            .filter(
                base_subq.c.status == "FAILED",
                base_subq.c.updated_at >= failed_since,
            )
            .label("failed_jobs_last_hours"),
            func.min(open_date_column)
            .filter(base_subq.c.status.in_(open_statuses))
            .label("oldest_open_job_date"),
        )
        .select_from(base_subq)
        .subquery()
    )


def oldest_open_support_job(base_subq, open_date_column, *extra_columns):
    return (
        select(base_subq.c.id, *extra_columns, base_subq.c.correlation_id)
        .where(base_subq.c.status.in_(("PENDING", "PROCESSING")))
        .order_by(
            open_date_column.asc(),
            base_subq.c.updated_at.asc(),
            base_subq.c.id.asc(),
        )
        .limit(1)
        .subquery()
    )


def support_job_health_thresholds(
    *,
    stale_minutes: int,
    failed_window_hours: int,
    reference_now: datetime,
):
    return (
        reference_now - timedelta(minutes=stale_minutes),
        reference_now - timedelta(hours=failed_window_hours),
    )


def support_job_health_result_select(
    aggregate_subq,
    oldest_job_subq,
    *,
    include_security: bool = False,
):
    selected_columns = [
        aggregate_subq.c.pending_jobs,
        aggregate_subq.c.processing_jobs,
        aggregate_subq.c.stale_processing_jobs,
        aggregate_subq.c.failed_jobs,
        aggregate_subq.c.failed_jobs_last_hours,
        aggregate_subq.c.oldest_open_job_date,
        oldest_job_subq.c.id,
        oldest_job_subq.c.correlation_id,
    ]
    if include_security:
        selected_columns.append(oldest_job_subq.c.security_id)
    return select(*selected_columns).select_from(aggregate_subq).outerjoin(oldest_job_subq, true())


def support_job_health_summary_from_row(
    row,
    *,
    include_security: bool = False,
) -> JobHealthSummary:
    return JobHealthSummary(
        pending_jobs=int_or_zero(row.pending_jobs),
        processing_jobs=int_or_zero(row.processing_jobs),
        stale_processing_jobs=int_or_zero(row.stale_processing_jobs),
        failed_jobs=int_or_zero(row.failed_jobs),
        failed_jobs_last_hours=int_or_zero(row.failed_jobs_last_hours),
        oldest_open_job_date=row.oldest_open_job_date,
        oldest_open_job_id=row.id,
        oldest_open_job_correlation_id=row.correlation_id,
        oldest_open_security_id=(
            normalize_security_id(row.security_id) if include_security else None
        ),
    )


def analytics_export_job_health_aggregate(
    base_subq,
    *,
    stale_threshold: datetime,
    failed_since: datetime,
):
    open_statuses = ("accepted", "running")
    return (
        select(
            func.count().filter(base_subq.c.status == "accepted").label("accepted_jobs"),
            func.count().filter(base_subq.c.status == "running").label("running_jobs"),
            func.count()
            .filter(
                base_subq.c.status == "running",
                base_subq.c.updated_at < stale_threshold,
            )
            .label("stale_running_jobs"),
            func.count().filter(base_subq.c.status == "failed").label("failed_jobs"),
            func.count()
            .filter(
                base_subq.c.status == "failed",
                base_subq.c.updated_at >= failed_since,
            )
            .label("failed_jobs_last_hours"),
            func.min(base_subq.c.created_at)
            .filter(base_subq.c.status.in_(open_statuses))
            .label("oldest_open_job_created_at"),
        )
        .select_from(base_subq)
        .subquery()
    )


def oldest_open_analytics_export_job(base_subq):
    return (
        select(
            base_subq.c.job_id,
            base_subq.c.request_fingerprint,
        )
        .where(base_subq.c.status.in_(("accepted", "running")))
        .order_by(
            base_subq.c.created_at.asc(),
            base_subq.c.updated_at.asc(),
            base_subq.c.job_id.asc(),
        )
        .limit(1)
        .subquery()
    )


def analytics_export_job_health_result_select(aggregate_subq, oldest_job_subq):
    return (
        select(
            aggregate_subq.c.accepted_jobs,
            aggregate_subq.c.running_jobs,
            aggregate_subq.c.stale_running_jobs,
            aggregate_subq.c.failed_jobs,
            aggregate_subq.c.failed_jobs_last_hours,
            aggregate_subq.c.oldest_open_job_created_at,
            oldest_job_subq.c.job_id,
            oldest_job_subq.c.request_fingerprint,
        )
        .select_from(aggregate_subq)
        .outerjoin(oldest_job_subq, true())
    )


def analytics_export_job_health_summary_from_row(row) -> ExportJobHealthSummary:
    return ExportJobHealthSummary(
        accepted_jobs=int_or_zero(row.accepted_jobs),
        running_jobs=int_or_zero(row.running_jobs),
        stale_running_jobs=int_or_zero(row.stale_running_jobs),
        failed_jobs=int_or_zero(row.failed_jobs),
        failed_jobs_last_hours=int_or_zero(row.failed_jobs_last_hours),
        oldest_open_job_created_at=row.oldest_open_job_created_at,
        oldest_open_job_id=row.job_id,
        oldest_open_request_fingerprint=row.request_fingerprint,
    )
