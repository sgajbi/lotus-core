from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ..dtos.analytics_input_dto import PositionAnalyticsTimeseriesRequest
from ..repositories.identifier_normalization import normalize_security_id
from .decimal_amounts import decimal_or_zero


@dataclass(frozen=True)
class PositionPageScope:
    page_dates: list[date]
    page_start_date: date
    page_end_date: date
    first_page_date: date
    security_ids: list[str]


def position_dimension_filters(
    request: PositionAnalyticsTimeseriesRequest,
) -> dict[str, set[str]]:
    return {item.dimension: set(item.values) for item in request.filters.dimension_filters}


def position_page_scope(
    *,
    rows_page: list[object],
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
    previous_rows: list[object],
    first_page_date: date,
) -> dict[str, Decimal]:
    previous_date = first_page_date - timedelta(days=1)
    return {
        normalize_security_id(row.security_id): decimal_or_zero(row.eod_market_value)
        for row in previous_rows
        if row.valuation_date == previous_date
    }
