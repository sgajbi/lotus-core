from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

from sqlalchemy import Integer, String, cast, column, func, select, tuple_, values
from sqlalchemy.orm import aliased
from sqlalchemy.types import Date

from .config import DEFAULT_BUSINESS_CALENDAR_CODE
from .database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    PositionHistory,
    PositionState,
)


def build_contiguous_snapshot_dates_stmt(
    states: List[PositionState],
    first_open_dates: Dict[Tuple[str, str, int], date],
):
    state_alias = aliased(PositionState)
    snapshot_alias = aliased(DailyPositionSnapshot)
    first_open_dates_table = _first_open_dates_table(first_open_dates)
    date_series_subq = _snapshot_date_series_subq(state_alias, first_open_dates_table)
    snapshot_quantity_matches_history = _snapshot_quantity_matches_history(snapshot_alias)
    first_gap_subq = _first_snapshot_gap_subq(
        state_alias,
        snapshot_alias,
        date_series_subq,
        snapshot_quantity_matches_history,
    )
    latest_snapshot_subq = _latest_matching_snapshot_subq(
        state_alias,
        snapshot_alias,
        snapshot_quantity_matches_history,
    )
    stmt = _base_contiguous_snapshot_dates_stmt(
        state_alias,
        _position_state_keys(states),
        first_gap_subq,
        latest_snapshot_subq,
    )
    return _join_first_open_dates_table(stmt, state_alias, first_open_dates_table)


def contiguous_snapshot_dates_by_key(result) -> Dict[Tuple[str, str], date]:
    return {(row.portfolio_id, row.security_id): row.contiguous_date for row in result}


def _position_state_keys(states: List[PositionState]) -> tuple[tuple[str, str, int], ...]:
    return tuple((state.portfolio_id, state.security_id, state.epoch) for state in states)


def _first_open_dates_table(first_open_dates: Dict[Tuple[str, str, int], date]):
    first_open_dates_rows = _first_open_date_rows(first_open_dates)
    if not first_open_dates_rows:
        return None
    return (
        values(
            column("portfolio_id", String),
            column("security_id", String),
            column("epoch", Integer),
            column("first_open_date", Date),
            name="first_open_dates",
        )
        .data(first_open_dates_rows)
        .alias("first_open_dates")
    )


def _first_open_date_rows(
    first_open_dates: Dict[Tuple[str, str, int], date],
) -> list[tuple[str, str, int, date]]:
    return [
        (
            portfolio_id,
            security_id,
            epoch,
            first_open_date,
        )
        for (portfolio_id, security_id, epoch), first_open_date in first_open_dates.items()
    ]


def _snapshot_date_series_subq(state_alias, first_open_dates_table):
    return (
        select(
            func.generate_series(
                _expected_snapshot_start_date(state_alias, first_open_dates_table),
                _max_business_date_subq(),
                timedelta(days=1),
            )
            .cast(Date)
            .label("expected_date")
        )
        .correlate(*_snapshot_date_series_correlates(state_alias, first_open_dates_table))
        .subquery("date_series")
    )


def _expected_snapshot_start_date(state_alias, first_open_dates_table):
    next_watermark_date = state_alias.watermark_date + timedelta(days=1)
    if first_open_dates_table is None:
        return cast(next_watermark_date, Date)
    return cast(
        func.greatest(
            next_watermark_date,
            func.coalesce(first_open_dates_table.c.first_open_date, next_watermark_date),
        ),
        Date,
    )


def _snapshot_date_series_correlates(state_alias, first_open_dates_table) -> tuple[Any, ...]:
    if first_open_dates_table is None:
        return (state_alias,)
    return (state_alias, first_open_dates_table)


def _max_business_date_subq():
    return (
        select(func.max(BusinessDate.date))
        .where(BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE)
        .scalar_subquery()
    )


def _snapshot_quantity_matches_history(snapshot_alias):
    latest_history_quantity_for_snapshot = _latest_history_quantity_for_snapshot(snapshot_alias)
    return latest_history_quantity_for_snapshot.is_(None) | (
        snapshot_alias.quantity == latest_history_quantity_for_snapshot
    )


def _latest_history_quantity_for_snapshot(snapshot_alias):
    return (
        select(PositionHistory.quantity)
        .where(
            PositionHistory.portfolio_id == snapshot_alias.portfolio_id,
            PositionHistory.security_id == snapshot_alias.security_id,
            PositionHistory.epoch == snapshot_alias.epoch,
            PositionHistory.position_date <= snapshot_alias.date,
        )
        .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
        .limit(1)
        .correlate(snapshot_alias)
        .scalar_subquery()
    )


def _first_snapshot_gap_subq(
    state_alias,
    snapshot_alias,
    date_series_subq,
    snapshot_quantity_matches_history,
):
    return (
        select(func.min(date_series_subq.c.expected_date))
        .select_from(
            date_series_subq.outerjoin(
                snapshot_alias,
                _matching_snapshot_on_expected_date(
                    state_alias,
                    snapshot_alias,
                    date_series_subq,
                    snapshot_quantity_matches_history,
                ),
            )
        )
        .where(snapshot_alias.id.is_(None))
        .correlate(state_alias)
        .scalar_subquery()
    )


def _matching_snapshot_on_expected_date(
    state_alias,
    snapshot_alias,
    date_series_subq,
    snapshot_quantity_matches_history,
):
    return (
        (snapshot_alias.portfolio_id == state_alias.portfolio_id)
        & (snapshot_alias.security_id == state_alias.security_id)
        & (snapshot_alias.epoch == state_alias.epoch)
        & (snapshot_alias.date == date_series_subq.c.expected_date)
        & snapshot_quantity_matches_history
    )


def _latest_matching_snapshot_subq(
    state_alias,
    snapshot_alias,
    snapshot_quantity_matches_history,
):
    return (
        select(func.max(snapshot_alias.date))
        .where(
            (snapshot_alias.portfolio_id == state_alias.portfolio_id)
            & (snapshot_alias.security_id == state_alias.security_id)
            & (snapshot_alias.epoch == state_alias.epoch)
            & snapshot_quantity_matches_history
        )
        .correlate(state_alias)
        .scalar_subquery()
    )


def _base_contiguous_snapshot_dates_stmt(
    state_alias,
    keys_tuple: tuple[tuple[str, str, int], ...],
    first_gap_subq,
    latest_snapshot_subq,
):
    return (
        select(
            state_alias.portfolio_id,
            state_alias.security_id,
            cast(
                func.coalesce(first_gap_subq - timedelta(days=1), latest_snapshot_subq),
                Date,
            ).label("contiguous_date"),
        )
        .select_from(state_alias)
        .where(
            tuple_(state_alias.portfolio_id, state_alias.security_id, state_alias.epoch).in_(
                keys_tuple
            ),
            latest_snapshot_subq.isnot(None),
        )
    )


def _join_first_open_dates_table(stmt, state_alias, first_open_dates_table):
    if first_open_dates_table is None:
        return stmt
    return stmt.outerjoin(
        first_open_dates_table,
        (first_open_dates_table.c.portfolio_id == state_alias.portfolio_id)
        & (first_open_dates_table.c.security_id == state_alias.security_id)
        & (first_open_dates_table.c.epoch == state_alias.epoch),
    )
