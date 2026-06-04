from __future__ import annotations

from datetime import date, datetime

from portfolio_common.database_models import (
    PortfolioAggregationJob,
    PortfolioValuationJob,
    PositionState,
)
from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import aliased

from .operations_position_scope_queries import security_id_expr


def support_job_status_filter(status_column, status: str):
    return status_column == status.strip().upper()


def is_actionable_valuation_job(*, as_of: datetime | None = None):
    superseding_job = aliased(PortfolioValuationJob)
    valuation_job_security_id = security_id_expr(PortfolioValuationJob.security_id)
    superseding_job_security_id = security_id_expr(superseding_job.security_id)
    superseded_pending_exists = select(superseding_job.id).where(
        superseding_job.portfolio_id == PortfolioValuationJob.portfolio_id,
        superseding_job_security_id == valuation_job_security_id,
        superseding_job.valuation_date == PortfolioValuationJob.valuation_date,
        superseding_job.epoch > PortfolioValuationJob.epoch,
    )
    if as_of is not None:
        superseded_pending_exists = superseded_pending_exists.where(
            superseding_job.updated_at <= as_of
        )

    return or_(
        PortfolioValuationJob.status != "PENDING",
        ~superseded_pending_exists.correlate(PortfolioValuationJob).exists(),
    )


def has_superseding_valuation_epoch(*, as_of: datetime | None = None):
    superseding_job = aliased(PortfolioValuationJob)
    valuation_job_security_id = security_id_expr(PortfolioValuationJob.security_id)
    superseding_job_security_id = security_id_expr(superseding_job.security_id)
    superseding_exists = select(superseding_job.id).where(
        superseding_job.portfolio_id == PortfolioValuationJob.portfolio_id,
        superseding_job_security_id == valuation_job_security_id,
        superseding_job.valuation_date == PortfolioValuationJob.valuation_date,
        superseding_job.epoch > PortfolioValuationJob.epoch,
    )
    if as_of is not None:
        superseding_exists = superseding_exists.where(superseding_job.updated_at <= as_of)
    return superseding_exists.correlate(PortfolioValuationJob).exists()


def latest_valuation_job_lateral(position_state_security_id, as_of):
    valuation_job_security_id = security_id_expr(PortfolioValuationJob.security_id)
    latest_valuation_job = select(
        PortfolioValuationJob.valuation_date.label("latest_valuation_job_date"),
        PortfolioValuationJob.id.label("latest_valuation_job_id"),
        PortfolioValuationJob.status.label("latest_valuation_job_status"),
        PortfolioValuationJob.correlation_id.label("latest_valuation_job_correlation_id"),
    ).where(
        PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
        valuation_job_security_id == position_state_security_id,
        PortfolioValuationJob.epoch == PositionState.epoch,
    )
    if as_of is not None:
        latest_valuation_job = latest_valuation_job.where(
            PortfolioValuationJob.created_at <= as_of,
            PortfolioValuationJob.updated_at <= as_of,
        )
    return (
        latest_valuation_job.order_by(
            PortfolioValuationJob.valuation_date.desc(),
            PortfolioValuationJob.id.desc(),
        )
        .limit(1)
        .correlate(PositionState)
        .lateral()
    )


def support_job_priority(status_column, updated_at_column, stale_threshold: datetime):
    governed_status = status_column
    return case(
        (governed_status == "FAILED", 0),
        (
            and_(governed_status == "PROCESSING", updated_at_column < stale_threshold),
            1,
        ),
        (governed_status == "PROCESSING", 2),
        (governed_status == "PENDING", 3),
        else_=9,
    )


def apply_valuation_actionable_scope(
    stmt,
    *,
    job_id: int | None,
    correlation_id: str | None,
    actionable_valuation_job,
):
    if job_id is None and correlation_id is None:
        return stmt.where(actionable_valuation_job)
    return stmt


def apply_valuation_identity_scope(
    stmt,
    *,
    job_id: int | None,
    correlation_id: str | None,
):
    if job_id is not None:
        stmt = stmt.where(PortfolioValuationJob.id == job_id)
    if correlation_id:
        stmt = stmt.where(PortfolioValuationJob.correlation_id == correlation_id)
    return stmt


def apply_valuation_attribute_scope(
    stmt,
    *,
    business_date: date | None,
    normalized_security_id: str | None,
):
    if business_date:
        stmt = stmt.where(PortfolioValuationJob.valuation_date == business_date)
    if normalized_security_id:
        valuation_job_security_id = security_id_expr(PortfolioValuationJob.security_id)
        stmt = stmt.where(valuation_job_security_id == normalized_security_id)
    return stmt


def apply_aggregation_identity_scope(
    stmt,
    *,
    job_id: int | None,
    correlation_id: str | None,
):
    if job_id is not None:
        stmt = stmt.where(PortfolioAggregationJob.id == job_id)
    if correlation_id:
        stmt = stmt.where(PortfolioAggregationJob.correlation_id == correlation_id)
    return stmt


def apply_aggregation_attribute_scope(
    stmt,
    *,
    business_date: date | None,
):
    if business_date:
        stmt = stmt.where(PortfolioAggregationJob.aggregation_date == business_date)
    return stmt


def apply_valuation_job_scope(
    stmt,
    *,
    portfolio_id: str,
    actionable_valuation_job,
    status: str | None = None,
    business_date: date | None = None,
    normalized_security_id: str | None = None,
    job_id: int | None = None,
    correlation_id: str | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(PortfolioValuationJob.portfolio_id == portfolio_id)
    stmt = apply_valuation_actionable_scope(
        stmt,
        job_id=job_id,
        correlation_id=correlation_id,
        actionable_valuation_job=actionable_valuation_job,
    )
    if as_of is not None:
        stmt = stmt.where(PortfolioValuationJob.updated_at <= as_of)
    if status:
        stmt = stmt.where(support_job_status_filter(PortfolioValuationJob.status, status))
    stmt = apply_valuation_attribute_scope(
        stmt,
        business_date=business_date,
        normalized_security_id=normalized_security_id,
    )
    stmt = apply_valuation_identity_scope(
        stmt,
        job_id=job_id,
        correlation_id=correlation_id,
    )
    return stmt


def apply_aggregation_job_scope(
    stmt,
    *,
    portfolio_id: str,
    status: str | None = None,
    business_date: date | None = None,
    job_id: int | None = None,
    correlation_id: str | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(PortfolioAggregationJob.portfolio_id == portfolio_id)
    if as_of is not None:
        stmt = stmt.where(PortfolioAggregationJob.updated_at <= as_of)
    if status:
        stmt = stmt.where(support_job_status_filter(PortfolioAggregationJob.status, status))
    stmt = apply_aggregation_attribute_scope(stmt, business_date=business_date)
    stmt = apply_aggregation_identity_scope(
        stmt,
        job_id=job_id,
        correlation_id=correlation_id,
    )
    return stmt
