from __future__ import annotations

from datetime import date, datetime

from portfolio_common.database_models import PositionHistory, PositionState, ReprocessingJob
from sqlalchemy import Date, and_, case, cast, func, select

from .operations_models import ResetWatermarkReprocessingJobScope
from .operations_position_scope_queries import (
    apply_current_position_history_scope,
    security_id_expr,
)
from .operations_support_job_queries import support_job_status_filter


def reprocessing_status_filter(status_column, status: str):
    return status_column == status.strip().upper()


def reprocessing_key_priority(status_column, updated_at_column, stale_threshold: datetime):
    governed_status = status_column
    return case(
        (
            and_(governed_status == "REPROCESSING", updated_at_column < stale_threshold),
            0,
        ),
        (governed_status == "REPROCESSING", 1),
        else_=9,
    )


def reprocessing_job_portfolio_scope_exists(
    portfolio_id: str,
    reprocessing_security_id_expr,
    impacted_date_expr,
):
    position_state_security_id = security_id_expr(PositionState.security_id)
    position_history_security_id = security_id_expr(PositionHistory.security_id)
    latest_history = select(
        PositionHistory.quantity.label("quantity"),
        func.row_number()
        .over(
            partition_by=PositionHistory.portfolio_id,
            order_by=[PositionHistory.position_date.desc(), PositionHistory.id.desc()],
        )
        .label("rn"),
    )
    latest_history = apply_current_position_history_scope(
        latest_history,
        portfolio_id=portfolio_id,
        position_history_security_id=position_history_security_id,
        position_state_security_id=position_state_security_id,
        normalized_security_id=reprocessing_security_id_expr,
        history_date_on_or_before=impacted_date_expr,
    )
    latest_history = latest_history.correlate(ReprocessingJob).subquery()

    return (
        select(1)
        .select_from(latest_history)
        .where(latest_history.c.rn == 1, latest_history.c.quantity > 0)
        .exists()
    )


def reset_watermark_reprocessing_job_scope(
    portfolio_id: str,
) -> ResetWatermarkReprocessingJobScope:
    reprocessing_security_id_expr = func.trim(ReprocessingJob.payload["security_id"].as_string())
    impacted_date_expr = ReprocessingJob.payload["earliest_impacted_date"].as_string()
    impacted_date_cast = cast(impacted_date_expr, Date)
    portfolio_scope_exists = reprocessing_job_portfolio_scope_exists(
        portfolio_id=portfolio_id,
        reprocessing_security_id_expr=reprocessing_security_id_expr,
        impacted_date_expr=impacted_date_cast,
    )
    return ResetWatermarkReprocessingJobScope(
        security_id_expr=reprocessing_security_id_expr,
        impacted_date_expr=impacted_date_expr,
        portfolio_scope_exists=portfolio_scope_exists,
    )


def apply_reprocessing_job_identity_scope(
    stmt,
    *,
    job_id: int | None,
    correlation_id: str | None,
):
    if job_id is not None:
        stmt = stmt.where(ReprocessingJob.id == job_id)
    if correlation_id:
        stmt = stmt.where(ReprocessingJob.correlation_id == correlation_id)
    return stmt


def apply_reprocessing_job_security_scope(
    stmt,
    *,
    reset_scope: ResetWatermarkReprocessingJobScope,
    normalized_security_id: str | None,
):
    if normalized_security_id:
        stmt = stmt.where(reset_scope.security_id_expr == normalized_security_id)
    return stmt


def apply_reprocessing_key_scope(
    stmt,
    *,
    portfolio_id: str,
    status: str | None = None,
    normalized_security_id: str | None = None,
    watermark_date: date | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(PositionState.portfolio_id == portfolio_id)
    if as_of is not None:
        stmt = stmt.where(PositionState.updated_at <= as_of)
    if status:
        stmt = stmt.where(reprocessing_status_filter(PositionState.status, status))
    if normalized_security_id:
        state_security_id = security_id_expr(PositionState.security_id)
        stmt = stmt.where(state_security_id == normalized_security_id)
    if watermark_date:
        stmt = stmt.where(PositionState.watermark_date == watermark_date)
    return stmt


def apply_reprocessing_job_scope(
    stmt,
    *,
    reset_scope: ResetWatermarkReprocessingJobScope,
    status: str | None = None,
    normalized_security_id: str | None = None,
    job_id: int | None = None,
    correlation_id: str | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(
        ReprocessingJob.job_type == "RESET_WATERMARKS",
        reset_scope.portfolio_scope_exists,
    )
    if as_of is not None:
        stmt = stmt.where(ReprocessingJob.updated_at <= as_of)
    if status:
        stmt = stmt.where(support_job_status_filter(ReprocessingJob.status, status))
    stmt = apply_reprocessing_job_security_scope(
        stmt,
        reset_scope=reset_scope,
        normalized_security_id=normalized_security_id,
    )
    stmt = apply_reprocessing_job_identity_scope(
        stmt,
        job_id=job_id,
        correlation_id=correlation_id,
    )
    return stmt
