"""Durable valuation outcome matching for selected portfolio history facts."""

from datetime import date
from typing import Any, Literal

from portfolio_common.portfolio_aggregation_job_schema import (
    PortfolioSelectedHistoryValuationState,
)
from sqlalchemy import and_, literal, or_, select
from sqlalchemy.sql.elements import ColumnElement


def selected_fact_valuation_outcome_handled(
    *,
    tenant_id: str,
    portfolio_id: str,
    selected: Any,
    valuation_outcome: Literal["READY", "UNAVAILABLE"] | None,
    delivered_epoch: int,
    delivered_date: date | None,
) -> ColumnElement[bool]:
    """Match a settled outcome or a newer event for the exact selected fact."""

    if valuation_outcome is None or delivered_date is None:
        return literal(False)
    state = PortfolioSelectedHistoryValuationState
    return (
        select(literal(1))
        .select_from(state)
        .where(
            state.tenant_id == tenant_id,
            state.portfolio_id == portfolio_id,
            state.security_id == selected.c.security_id,
            state.position_history_id == selected.c.history_id,
            state.source_fact == selected.c.source_fact,
            or_(
                state.valuation_outcome == valuation_outcome,
                state.valuation_epoch > delivered_epoch,
                and_(
                    state.valuation_epoch == delivered_epoch,
                    state.valuation_date > delivered_date,
                ),
            ),
        )
        .exists()
    )
