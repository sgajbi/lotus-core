from __future__ import annotations

from datetime import date, datetime

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    PositionHistory,
    PositionState,
    Transaction,
)
from sqlalchemy import and_, func, select

from .date_filters import start_of_next_day


def apply_load_run_artifact_scope(
    stmt,
    artifact_model,
    *,
    portfolio_pattern: str,
    business_date: date | None = None,
    as_of: datetime | None = None,
):
    stmt = stmt.where(artifact_model.portfolio_id.like(portfolio_pattern))
    if business_date is not None:
        stmt = stmt.where(artifact_model.date == business_date)
    if as_of is not None:
        stmt = stmt.where(artifact_model.created_at <= as_of)
    return stmt


def apply_load_run_job_scope(
    stmt,
    job_model,
    *,
    portfolio_pattern: str,
    as_of: datetime | None = None,
):
    stmt = stmt.where(job_model.portfolio_id.like(portfolio_pattern))
    if as_of is not None:
        stmt = stmt.where(job_model.updated_at <= as_of)
    return stmt


def apply_portfolio_security_epoch_scope(
    stmt,
    evidence_model,
    security_id_expr,
    *,
    portfolio_id: str,
    normalized_security_id: str,
    epoch: int,
    as_of: datetime | None = None,
    as_of_columns=(),
):
    stmt = stmt.where(
        evidence_model.portfolio_id == portfolio_id,
        security_id_expr == normalized_security_id,
        evidence_model.epoch == epoch,
    )
    if as_of is not None:
        for as_of_column in as_of_columns:
            stmt = stmt.where(as_of_column <= as_of)
    return stmt


def security_id_expr(security_id_column):
    return func.trim(security_id_column)


def position_history_security_expressions(
    *,
    position_history_security_id=None,
    position_state_security_id=None,
):
    return (
        position_history_security_id
        if position_history_security_id is not None
        else security_id_expr(PositionHistory.security_id),
        position_state_security_id
        if position_state_security_id is not None
        else security_id_expr(PositionState.security_id),
    )


def apply_position_history_security_scope(
    stmt,
    *,
    position_history_security_id,
    position_state_security_id,
    normalized_security_id=None,
):
    if normalized_security_id is None:
        return stmt
    return stmt.where(
        position_history_security_id == normalized_security_id,
        position_state_security_id == normalized_security_id,
    )


def apply_position_history_time_scope(
    stmt,
    *,
    history_date_on_or_before=None,
    history_as_of: datetime | None = None,
):
    if history_date_on_or_before is not None:
        stmt = stmt.where(PositionHistory.position_date <= history_date_on_or_before)
    if history_as_of is not None:
        stmt = stmt.where(
            PositionHistory.created_at <= history_as_of,
            PositionState.updated_at <= history_as_of,
        )
    return stmt


def apply_current_position_history_scope(
    stmt,
    *,
    portfolio_id: str,
    position_history_security_id=None,
    position_state_security_id=None,
    normalized_security_id=None,
    history_date_on_or_before=None,
    history_as_of: datetime | None = None,
):
    (
        position_history_security_id,
        position_state_security_id,
    ) = position_history_security_expressions(
        position_history_security_id=position_history_security_id,
        position_state_security_id=position_state_security_id,
    )
    stmt = stmt.join(
        PositionState,
        and_(
            PositionHistory.portfolio_id == PositionState.portfolio_id,
            position_history_security_id == position_state_security_id,
            PositionHistory.epoch == PositionState.epoch,
        ),
    ).where(PositionHistory.portfolio_id == portfolio_id)
    stmt = apply_position_history_security_scope(
        stmt,
        position_history_security_id=position_history_security_id,
        position_state_security_id=position_state_security_id,
        normalized_security_id=normalized_security_id,
    )
    return apply_position_history_time_scope(
        stmt,
        history_date_on_or_before=history_date_on_or_before,
        history_as_of=history_as_of,
    )


def current_epoch_snapshot_date_stmt(
    *,
    portfolio_id: str,
    as_of_date: date | None = None,
    snapshot_as_of: datetime | None = None,
):
    return apply_current_epoch_snapshot_scope(
        select(func.max(DailyPositionSnapshot.date)),
        portfolio_id=portfolio_id,
        as_of_date=as_of_date,
        snapshot_as_of=snapshot_as_of,
    )


def apply_current_epoch_snapshot_scope(
    stmt,
    *,
    portfolio_id: str,
    snapshot_date: date | None = None,
    as_of_date: date | None = None,
    snapshot_as_of: datetime | None = None,
):
    snapshot_security_id = security_id_expr(DailyPositionSnapshot.security_id)
    state_security_id = security_id_expr(PositionState.security_id)
    stmt = stmt.join(
        PositionState,
        and_(
            DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
            snapshot_security_id == state_security_id,
            DailyPositionSnapshot.epoch == PositionState.epoch,
        ),
    ).where(DailyPositionSnapshot.portfolio_id == portfolio_id)
    if snapshot_date is not None:
        stmt = stmt.where(DailyPositionSnapshot.date == snapshot_date)
    if as_of_date is not None:
        stmt = stmt.where(DailyPositionSnapshot.date <= as_of_date)
    if snapshot_as_of is not None:
        stmt = stmt.where(
            DailyPositionSnapshot.created_at <= snapshot_as_of,
            PositionState.updated_at <= snapshot_as_of,
        )
    return stmt


def latest_transaction_date_stmt(
    *,
    portfolio_id: str,
    as_of_date: date | None = None,
    snapshot_as_of: datetime | None = None,
):
    stmt = select(func.max(Transaction.transaction_date)).where(
        Transaction.portfolio_id == portfolio_id
    )
    if as_of_date is not None:
        stmt = stmt.where(Transaction.transaction_date < start_of_next_day(as_of_date))
    if snapshot_as_of is not None:
        stmt = stmt.where(Transaction.created_at <= snapshot_as_of)
    return stmt
