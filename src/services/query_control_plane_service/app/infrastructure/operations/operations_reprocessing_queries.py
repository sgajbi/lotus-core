"""SQL query policies for governed reprocessing jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from portfolio_common.database_models import (
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    ReprocessingJob,
)
from sqlalchemy import Date, and_, case, cast, func, or_, select

from .operations_position_scope_queries import (
    apply_current_position_history_scope,
    security_id_expr,
)
from .operations_support_job_queries import support_job_status_filter


@dataclass(frozen=True)
class ReprocessingJobScope:
    """SQL expressions that scope durable replay work to one portfolio."""

    portfolio_id: str
    security_id_expr: Any
    impacted_date_expr: Any
    from_currency_expr: Any
    to_currency_expr: Any
    portfolio_scope_exists: Any


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


def fx_revaluation_job_portfolio_scope_exists(
    *,
    portfolio_id: str,
    from_currency_expr,
    to_currency_expr,
    impacted_date_expr,
    normalized_security_id: str | None = None,
):
    """Return pair-scoped impact matching the valuation replay policy."""
    state_security_id = security_id_expr(PositionState.security_id)
    history_security_id = security_id_expr(PositionHistory.security_id)
    instrument_security_id = security_id_expr(Instrument.security_id)
    portfolio_identity = func.trim(Portfolio.portfolio_id)
    position_state_join = and_(
        PositionState.portfolio_id == PositionHistory.portfolio_id,
        state_security_id == history_security_id,
        PositionState.epoch == PositionHistory.epoch,
    )
    pair_scope = and_(
        PositionHistory.portfolio_id == portfolio_id,
        func.upper(func.trim(Instrument.currency)) == from_currency_expr,
        func.upper(func.trim(Portfolio.base_currency)) == to_currency_expr,
    )
    if normalized_security_id:
        pair_scope = and_(pair_scope, history_security_id == normalized_security_id)

    latest_history = (
        select(
            PositionHistory.quantity.label("quantity"),
            func.row_number()
            .over(
                partition_by=(
                    PositionHistory.portfolio_id,
                    PositionHistory.security_id,
                    PositionHistory.epoch,
                ),
                order_by=(
                    PositionHistory.position_date.desc(),
                    PositionHistory.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .select_from(PositionHistory)
        .join(PositionState, position_state_join)
        .join(Instrument, instrument_security_id == history_security_id)
        .join(Portfolio, portfolio_identity == func.trim(PositionHistory.portfolio_id))
        .where(
            pair_scope,
            PositionHistory.position_date <= impacted_date_expr,
        )
        .correlate(ReprocessingJob)
        .subquery()
    )
    open_on_date = (
        select(1)
        .select_from(latest_history)
        .where(latest_history.c.row_number == 1, latest_history.c.quantity > 0)
        .exists()
    )
    first_held_later = (
        select(1)
        .select_from(PositionHistory)
        .join(PositionState, position_state_join)
        .join(Instrument, instrument_security_id == history_security_id)
        .join(Portfolio, portfolio_identity == func.trim(PositionHistory.portfolio_id))
        .where(
            pair_scope,
            PositionHistory.position_date > impacted_date_expr,
            PositionHistory.quantity > 0,
        )
        .correlate(ReprocessingJob)
        .exists()
    )
    return or_(open_on_date, first_held_later)


def reprocessing_job_scope(portfolio_id: str) -> ReprocessingJobScope:
    """Build portfolio scope for security-price and direct-pair FX replay jobs."""
    reprocessing_security_id_expr = func.trim(ReprocessingJob.payload["security_id"].as_string())
    impacted_date_expr = ReprocessingJob.payload["earliest_impacted_date"].as_string()
    impacted_date_cast = cast(impacted_date_expr, Date)
    reset_portfolio_scope_exists = reprocessing_job_portfolio_scope_exists(
        portfolio_id=portfolio_id,
        reprocessing_security_id_expr=reprocessing_security_id_expr,
        impacted_date_expr=impacted_date_cast,
    )
    from_currency_expr = func.upper(func.trim(ReprocessingJob.payload["from_currency"].as_string()))
    to_currency_expr = func.upper(func.trim(ReprocessingJob.payload["to_currency"].as_string()))
    fx_portfolio_scope_exists = fx_revaluation_job_portfolio_scope_exists(
        portfolio_id=portfolio_id,
        from_currency_expr=from_currency_expr,
        to_currency_expr=to_currency_expr,
        impacted_date_expr=impacted_date_cast,
    )
    return ReprocessingJobScope(
        portfolio_id=portfolio_id,
        security_id_expr=reprocessing_security_id_expr,
        impacted_date_expr=impacted_date_expr,
        from_currency_expr=from_currency_expr,
        to_currency_expr=to_currency_expr,
        portfolio_scope_exists=or_(
            and_(
                ReprocessingJob.job_type == "RESET_WATERMARKS",
                reset_portfolio_scope_exists,
            ),
            and_(
                ReprocessingJob.job_type == "RESET_FX_WATERMARKS",
                fx_portfolio_scope_exists,
            ),
        ),
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
    job_scope: ReprocessingJobScope,
    normalized_security_id: str | None,
):
    if normalized_security_id:
        fx_security_scope_exists = fx_revaluation_job_portfolio_scope_exists(
            portfolio_id=job_scope.portfolio_id,
            from_currency_expr=job_scope.from_currency_expr,
            to_currency_expr=job_scope.to_currency_expr,
            impacted_date_expr=cast(job_scope.impacted_date_expr, Date),
            normalized_security_id=normalized_security_id,
        )
        stmt = stmt.where(
            or_(
                and_(
                    ReprocessingJob.job_type == "RESET_WATERMARKS",
                    job_scope.security_id_expr == normalized_security_id,
                ),
                and_(
                    ReprocessingJob.job_type == "RESET_FX_WATERMARKS",
                    fx_security_scope_exists,
                ),
            )
        )
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
    job_scope: ReprocessingJobScope,
    status: str | None = None,
    normalized_security_id: str | None = None,
    job_id: int | None = None,
    correlation_id: str | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(job_scope.portfolio_scope_exists)
    if as_of is not None:
        stmt = stmt.where(ReprocessingJob.updated_at <= as_of)
    if status:
        stmt = stmt.where(support_job_status_filter(ReprocessingJob.status, status))
    stmt = apply_reprocessing_job_security_scope(
        stmt,
        job_scope=job_scope,
        normalized_security_id=normalized_security_id,
    )
    stmt = apply_reprocessing_job_identity_scope(
        stmt,
        job_id=job_id,
        correlation_id=correlation_id,
    )
    return stmt
