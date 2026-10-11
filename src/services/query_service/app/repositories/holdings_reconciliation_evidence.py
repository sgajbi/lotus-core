"""Read the dated source cohort independently of the open-position projection."""

from datetime import date

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..application.holdings_reconciliation import HoldingsReconciliationEvidence


async def read_holdings_reconciliation_evidence(
    db: AsyncSession, *, portfolio_id: str, as_of_date: date | None
) -> list[HoldingsReconciliationEvidence]:
    """Retain zero rows and mismatched/missing evidence for fail-closed qualification.

    Rank dated facts before comparing their source epochs to current state. Neither
    quantity nor a successful stored control determines source-cohort membership.
    """
    history_security = func.trim(PositionHistory.security_id)
    snapshot_security = func.trim(DailyPositionSnapshot.security_id)
    latest_history = (
        select(PositionHistory)
        .where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.position_date <= as_of_date if as_of_date is not None else True,
        )
        .distinct(history_security)
        .order_by(
            history_security,
            PositionHistory.position_date.desc(),
            PositionHistory.epoch.desc(),
            PositionHistory.id.desc(),
        )
        .subquery()
    )
    latest_snapshot = (
        select(DailyPositionSnapshot)
        .where(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.date <= as_of_date if as_of_date is not None else True,
        )
        .distinct(snapshot_security)
        .order_by(
            snapshot_security,
            DailyPositionSnapshot.date.desc(),
            DailyPositionSnapshot.epoch.desc(),
            DailyPositionSnapshot.id.desc(),
        )
        .subquery()
    )
    history = aliased(PositionHistory, latest_history)
    snapshot = aliased(DailyPositionSnapshot, latest_snapshot)
    state = aliased(
        PositionState,
        select(PositionState)
        .where(
            PositionState.portfolio_id == portfolio_id,
        )
        .subquery(),
    )
    history_state_security = func.coalesce(
        func.trim(history.security_id), func.trim(state.security_id)
    )
    cohort_security = func.coalesce(history_state_security, func.trim(snapshot.security_id))
    statement = (
        select(
            history,
            snapshot,
            Instrument,
            state,
            Portfolio.base_currency,
            func.greatest(Portfolio.created_at, Portfolio.updated_at),
        )
        .select_from(history)
        .join(
            state,
            and_(
                state.portfolio_id == history.portfolio_id,
                func.trim(state.security_id) == func.trim(history.security_id),
            ),
            full=True,
        )
        .join(
            snapshot,
            and_(
                snapshot.portfolio_id == func.coalesce(history.portfolio_id, state.portfolio_id),
                func.trim(snapshot.security_id) == history_state_security,
            ),
            full=True,
        )
        .outerjoin(Instrument, func.trim(Instrument.security_id) == cohort_security)
        .outerjoin(
            Portfolio,
            Portfolio.portfolio_id
            == func.coalesce(
                history.portfolio_id,
                state.portfolio_id,
                snapshot.portfolio_id,
            ),
        )
        .where(
            or_(
                history.id.is_not(None),
                snapshot.id.is_not(None),
                state.watermark_date <= as_of_date
                if as_of_date is not None
                else state.watermark_date.is_not(None),
            )
        )
        .order_by(cohort_security)
    )
    return [HoldingsReconciliationEvidence(*row) for row in (await db.execute(statement)).all()]
