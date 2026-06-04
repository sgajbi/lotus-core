from __future__ import annotations

from datetime import datetime

from portfolio_common.database_models import PositionState
from sqlalchemy import and_, case, func, select, true


def lineage_latest_date_subquery(
    model,
    date_column,
    security_id_expr,
    position_state_security_id,
    *,
    as_of_column=None,
    as_of: datetime | None = None,
):
    stmt = select(func.max(date_column)).where(
        model.portfolio_id == PositionState.portfolio_id,
        security_id_expr == position_state_security_id,
        model.epoch == PositionState.epoch,
    )
    if as_of is not None and as_of_column is not None:
        stmt = stmt.where(as_of_column <= as_of)
    return stmt.correlate(PositionState).scalar_subquery()


def lineage_artifact_gap_case(
    *,
    latest_position_history_date,
    latest_daily_snapshot_date,
    latest_valuation_job_date,
    latest_valuation_job_status,
):
    return case(
        (latest_position_history_date.is_(None), False),
        (latest_daily_snapshot_date.is_(None), True),
        (latest_daily_snapshot_date < latest_position_history_date, True),
        (latest_valuation_job_date.is_(None), True),
        (latest_valuation_job_date < latest_position_history_date, True),
        (latest_valuation_job_status.in_(("FAILED", "PENDING", "PROCESSING")), True),
        else_=False,
    )


def lineage_priority_case(*, has_artifact_gap, latest_valuation_job_status):
    return case(
        (PositionState.status == "REPROCESSING", 0),
        (
            and_(has_artifact_gap.is_(True), latest_valuation_job_status == "FAILED"),
            1,
        ),
        (has_artifact_gap.is_(True), 2),
        else_=9,
    )


def lineage_keys_select(
    *,
    position_state_security_id,
    latest_position_history_date,
    latest_daily_snapshot_date,
    latest_valuation_job,
):
    return (
        select(
            position_state_security_id.label("security_id"),
            PositionState.epoch,
            PositionState.watermark_date,
            PositionState.status.label("reprocessing_status"),
            latest_position_history_date.label("latest_position_history_date"),
            latest_daily_snapshot_date.label("latest_daily_snapshot_date"),
            latest_valuation_job.c.latest_valuation_job_date.label("latest_valuation_job_date"),
            latest_valuation_job.c.latest_valuation_job_id.label("latest_valuation_job_id"),
            latest_valuation_job.c.latest_valuation_job_status.label("latest_valuation_job_status"),
            latest_valuation_job.c.latest_valuation_job_correlation_id.label(
                "latest_valuation_job_correlation_id"
            ),
        )
        .select_from(PositionState)
        .outerjoin(latest_valuation_job, true())
    )
