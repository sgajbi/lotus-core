from __future__ import annotations

from datetime import date, datetime

from portfolio_common.database_models import PortfolioAggregationJob, PortfolioValuationJob

from .operations_position_scope_queries import security_id_expr


def support_job_status_filter(status_column, status: str):
    return status_column == status.strip().upper()


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
