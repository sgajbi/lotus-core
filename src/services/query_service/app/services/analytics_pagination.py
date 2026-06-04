from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from ..dtos.analytics_input_dto import (
    AnalyticsWindow,
    PortfolioAnalyticsTimeseriesRequest,
    PortfolioQualityDiagnostics,
    PositionAnalyticsTimeseriesRequest,
    QualityDiagnostics,
)
from ..repositories.identifier_normalization import normalize_security_id
from .request_fingerprint import request_fingerprint


class AnalyticsPaginationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PositionTimeseriesCursor:
    cursor_date: date | None
    cursor_security_id: str | None
    snapshot_epoch: int | None


def portfolio_timeseries_scope_fingerprint(
    *,
    portfolio_id: str,
    request: PortfolioAnalyticsTimeseriesRequest,
    resolved_window: AnalyticsWindow,
    reporting_currency: str,
) -> str:
    return request_fingerprint(
        {
            "endpoint": "portfolio-timeseries",
            "portfolio_id": portfolio_id,
            "as_of_date": request.as_of_date.isoformat(),
            "resolved_window": resolved_window.model_dump(mode="json"),
            "frequency": request.frequency,
            "reporting_currency": reporting_currency,
        }
    )


def portfolio_timeseries_cursor_date(
    *,
    page_token: str | None,
    request_scope_fingerprint: str,
    decode_page_token: Callable[[str | None], dict],
) -> date | None:
    cursor = decode_page_token(page_token)
    token_scope = cursor.get("scope_fingerprint")
    if token_scope is not None and token_scope != request_scope_fingerprint:
        raise AnalyticsPaginationError("Page token does not match request scope.")
    if not cursor.get("valuation_date"):
        return None
    return date.fromisoformat(cursor["valuation_date"])


def portfolio_timeseries_diagnostics(
    *,
    quality_distribution: dict[str, int],
    expected_business_dates: list[date],
    observed_dates: list[date],
) -> PortfolioQualityDiagnostics:
    observed_date_set = set(observed_dates)
    missing_dates_count = sum(
        1 for expected_date in expected_business_dates if expected_date not in observed_date_set
    )
    stale_points_count = stale_points_count_from_distribution(quality_distribution)
    return PortfolioQualityDiagnostics(
        quality_status_distribution=quality_distribution,
        missing_dates_count=missing_dates_count,
        stale_points_count=stale_points_count,
        expected_business_dates_count=len(expected_business_dates),
        returned_observation_dates_count=len(observed_dates),
        cash_flows_included=True,
    )


def position_timeseries_scope_fingerprint(
    *,
    portfolio_id: str,
    request: PositionAnalyticsTimeseriesRequest,
    resolved_window: AnalyticsWindow,
    reporting_currency: str,
) -> str:
    return request_fingerprint(
        {
            "endpoint": "position-timeseries",
            "portfolio_id": portfolio_id,
            "as_of_date": request.as_of_date.isoformat(),
            "resolved_window": resolved_window.model_dump(mode="json"),
            "frequency": request.frequency,
            "reporting_currency": reporting_currency,
            "security_ids": request.filters.security_ids,
            "position_ids": request.filters.position_ids,
            "dimension_filters": [
                f.model_dump(mode="json") for f in request.filters.dimension_filters
            ],
            "dimensions": request.dimensions,
            "include_cash_flows": request.include_cash_flows,
        }
    )


def position_timeseries_cursor(
    *,
    page_token: str | None,
    request_scope_fingerprint: str,
    decode_page_token: Callable[[str | None], dict],
) -> PositionTimeseriesCursor:
    cursor = decode_page_token(page_token)
    token_scope = cursor.get("scope_fingerprint")
    if token_scope is not None and token_scope != request_scope_fingerprint:
        raise AnalyticsPaginationError("Page token does not match request scope.")
    return PositionTimeseriesCursor(
        cursor_date=(
            date.fromisoformat(cursor["valuation_date"]) if cursor.get("valuation_date") else None
        ),
        cursor_security_id=cursor.get("security_id"),
        snapshot_epoch=(int(cursor["snapshot_epoch"]) if cursor.get("snapshot_epoch") else None),
    )


def position_timeseries_next_page_token(
    *,
    has_more: bool,
    rows_page: list[object],
    snapshot_epoch: int,
    request_scope_fingerprint: str,
    encode_page_token: Callable[[dict], str],
) -> str | None:
    if not has_more or not rows_page:
        return None
    last = rows_page[-1]
    return encode_page_token(
        {
            "valuation_date": last.valuation_date.isoformat(),
            "security_id": normalize_security_id(last.security_id),
            "snapshot_epoch": snapshot_epoch,
            "scope_fingerprint": request_scope_fingerprint,
        }
    )


def position_timeseries_diagnostics(
    *,
    quality_distribution: dict[str, int],
    dimensions: list[str],
    include_cash_flows: bool,
) -> QualityDiagnostics:
    stale_points_count = stale_points_count_from_distribution(quality_distribution)
    return QualityDiagnostics(
        quality_status_distribution=quality_distribution,
        missing_dates_count=0,
        stale_points_count=stale_points_count,
        requested_dimensions=list(dimensions),
        cash_flows_included=include_cash_flows,
    )


def stale_points_count_from_distribution(quality_distribution: dict[str, int]) -> int:
    return sum(
        count for status_name, count in quality_distribution.items() if status_name != "final"
    )
