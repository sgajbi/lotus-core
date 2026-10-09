"""Position analytics page scope and filter policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.domain.decimal_amount import decimal_or_zero
from portfolio_common.identifiers import normalize_lookup_identifier as normalize_security_id

from ...contracts.analytics_inputs import (
    CashFlowObservation,
    PositionAnalyticsTimeseriesRequest,
    PositionTimeseriesRow,
)
from ...domain.analytics import PositionValuationObservation, PriorPositionValuation
from .analytics_pagination import PositionTimeseriesCursor


@dataclass(frozen=True)
class PositionPageScope:
    page_dates: list[date]
    page_start_date: date
    page_end_date: date
    first_page_date: date
    security_ids: list[str]


@dataclass(frozen=True)
class PositionPageSupportInputs:
    position_cashflows_by_key: dict[tuple[str, date], list[CashFlowObservation]]
    portfolio_cashflows_by_date: dict[date, list[CashFlowObservation]]
    position_to_portfolio_rates: dict[str, dict[date, Decimal]]
    fx_rates: dict[date, Decimal]
    previous_eod_by_security: dict[str, Decimal]
    selected_inputs_fingerprint: str = ""


def position_traversal_page(
    *,
    rows: list[PositionValuationObservation],
    response_rows: list[PositionTimeseriesRow],
    cursor: PositionTimeseriesCursor,
    page_size: int,
) -> tuple[list[PositionValuationObservation], list[PositionTimeseriesRow], dict[str, int], bool]:
    """Page an acquired window without discarding prior-row continuity during rendering."""
    selected = [
        (row, response)
        for row, response in zip(rows, response_rows, strict=True)
        if cursor.cursor_date is None
        or (row.valuation_date, normalize_security_id(row.security_id))
        > (cursor.cursor_date, cursor.cursor_security_id or "")
    ]
    page = selected[:page_size]
    quality: dict[str, int] = {}
    for _, response in page:
        quality[response.valuation_status] = quality.get(response.valuation_status, 0) + 1
    return (
        [row for row, _ in page],
        [response for _, response in page],
        quality,
        len(selected) > page_size,
    )


def position_dimension_filters(
    request: PositionAnalyticsTimeseriesRequest,
) -> dict[str, set[str]]:
    return {item.dimension: set(item.values) for item in request.filters.dimension_filters}


def position_page_scope(
    *,
    rows_page: list[PositionValuationObservation],
    fallback_start_date: date,
) -> PositionPageScope:
    page_dates = sorted({row.valuation_date for row in rows_page})
    return PositionPageScope(
        page_dates=page_dates,
        page_start_date=min(page_dates, default=fallback_start_date),
        page_end_date=max(page_dates, default=fallback_start_date),
        first_page_date=min(row.valuation_date for row in rows_page),
        security_ids=sorted(
            {
                security_id
                for row in rows_page
                if (security_id := normalize_security_id(row.security_id))
            }
        ),
    )


def previous_position_eod_by_security(
    *,
    previous_rows: list[PriorPositionValuation],
    first_page_date: date,
) -> dict[str, Decimal]:
    del first_page_date  # Date authority is enforced by the repository's business-calendar query.
    return {
        normalize_security_id(row.security_id): decimal_or_zero(row.eod_market_value)
        for row in previous_rows
    }
