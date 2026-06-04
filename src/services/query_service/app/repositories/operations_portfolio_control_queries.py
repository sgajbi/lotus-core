from __future__ import annotations

from datetime import date, datetime

from portfolio_common.database_models import PipelineStageState
from sqlalchemy import case


def portfolio_control_status_filter(status_column, status: str):
    return status_column == status.strip().upper()


def portfolio_control_stage_priority(status_column):
    governed_status = status_column
    return case(
        (governed_status.in_(("FAILED", "REQUIRES_REPLAY")), 0),
        else_=9,
    )


def apply_portfolio_control_stage_identity_scope(
    stmt,
    *,
    stage_id: int | None,
    stage_name: str | None,
):
    if stage_id is not None:
        stmt = stmt.where(PipelineStageState.id == stage_id)
    if stage_name:
        stmt = stmt.where(PipelineStageState.stage_name == stage_name)
    return stmt


def apply_portfolio_control_stage_attribute_scope(
    stmt,
    *,
    business_date: date | None,
):
    if business_date:
        stmt = stmt.where(PipelineStageState.business_date == business_date)
    return stmt


def apply_portfolio_control_stage_scope(
    stmt,
    *,
    portfolio_id: str,
    stage_id: int | None = None,
    stage_name: str | None = None,
    business_date: date | None = None,
    status: str | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(
        PipelineStageState.portfolio_id == portfolio_id,
        PipelineStageState.transaction_id.like("portfolio-stage:%"),
    )
    if as_of is not None:
        stmt = stmt.where(PipelineStageState.updated_at <= as_of)
    stmt = apply_portfolio_control_stage_identity_scope(
        stmt,
        stage_id=stage_id,
        stage_name=stage_name,
    )
    stmt = apply_portfolio_control_stage_attribute_scope(
        stmt,
        business_date=business_date,
    )
    if status:
        stmt = stmt.where(portfolio_control_status_filter(PipelineStageState.status, status))
    return stmt
