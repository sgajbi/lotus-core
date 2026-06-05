from __future__ import annotations

from datetime import date, datetime

from portfolio_common.reconciliation_quality import (
    COMPLETE,
    PARTIAL,
    DataQualityCoverageSignal,
    classify_data_quality_coverage,
)


def quality_status_from_epoch(epoch: int) -> str:
    if epoch > 0:
        return "restated"
    return "final"


def timeseries_data_quality_status(
    *,
    required_count: int,
    observed_count: int,
    stale_count: int,
    warning_issue_count: int = 0,
) -> str:
    return classify_data_quality_coverage(
        DataQualityCoverageSignal(
            required_count=required_count,
            observed_count=observed_count,
            stale_count=stale_count,
            warning_issue_count=warning_issue_count,
        )
    )


def portfolio_reference_data_quality_status(*, performance_end_date: date | None) -> str:
    return COMPLETE if performance_end_date is not None else PARTIAL


def portfolio_reference_evidence_timestamp(portfolio: object) -> datetime | None:
    timestamps = [
        timestamp
        for field_name in ("source_timestamp", "updated_at", "created_at")
        if isinstance(timestamp := getattr(portfolio, field_name, None), datetime)
    ]
    return max(timestamps) if timestamps else None


def latest_position_horizon_with_observations(
    *,
    latest_position_date: date | None,
    observed_dates: list[date] | None,
) -> date | None:
    if not observed_dates:
        return latest_position_date
    observed_latest = max(observed_dates)
    return (
        observed_latest
        if latest_position_date is None
        else max(latest_position_date, observed_latest)
    )


def latest_portfolio_horizon_candidate(
    *,
    latest_portfolio_date: date | None,
    observed_dates: list[date] | None,
) -> date | None:
    portfolio_dates = [
        candidate for candidate in (latest_portfolio_date, *(observed_dates or [])) if candidate
    ]
    return max(portfolio_dates) if portfolio_dates else None


def bounded_latest_performance_date(
    *,
    portfolio_candidate: date | None,
    latest_position_date: date | None,
    as_of_date: date,
) -> date | None:
    horizon_candidates = performance_horizon_candidates(
        portfolio_candidate=portfolio_candidate,
        latest_position_date=latest_position_date,
    )
    if not horizon_candidates:
        return None
    return min(*horizon_candidates, as_of_date)


def performance_horizon_candidates(
    *,
    portfolio_candidate: date | None,
    latest_position_date: date | None,
) -> list[date]:
    return [
        candidate
        for candidate in (portfolio_candidate, latest_position_date)
        if candidate is not None
    ]
