from __future__ import annotations

from datetime import date, timedelta

from ..dtos.analytics_input_dto import AnalyticsWindow


class AnalyticsWindowError(ValueError):
    pass


def resolve_analytics_window(
    *,
    as_of_date: date,
    window: AnalyticsWindow | None,
    period: str | None,
    inception_date: date,
) -> AnalyticsWindow:
    if window is not None:
        return bounded_explicit_analytics_window(window=window, as_of_date=as_of_date)

    return AnalyticsWindow(
        start_date=clamped_period_start_date(
            as_of_date=as_of_date,
            period=period,
            inception_date=inception_date,
        ),
        end_date=as_of_date,
    )


def bounded_explicit_analytics_window(
    *,
    window: AnalyticsWindow,
    as_of_date: date,
) -> AnalyticsWindow:
    end_date = min(window.end_date, as_of_date)
    if window.start_date > end_date:
        raise AnalyticsWindowError("window.start_date must be before or equal to end_date.")
    return AnalyticsWindow(start_date=window.start_date, end_date=end_date)


def clamped_period_start_date(
    *,
    as_of_date: date,
    period: str | None,
    inception_date: date,
) -> date:
    start_date = period_start_date(
        as_of_date=as_of_date,
        period=period,
        inception_date=inception_date,
    )
    return max(start_date, inception_date)


def period_start_date(
    *,
    as_of_date: date,
    period: str | None,
    inception_date: date,
) -> date:
    period_start_dates = {
        "one_month": as_of_date - timedelta(days=31),
        "three_months": as_of_date - timedelta(days=92),
        "ytd": date(as_of_date.year, 1, 1),
        "one_year": as_of_date - timedelta(days=365),
        "three_years": as_of_date - timedelta(days=365 * 3),
        "five_years": as_of_date - timedelta(days=365 * 5),
        "inception": inception_date,
    }
    if period not in period_start_dates:
        raise AnalyticsWindowError("Unsupported period value.")
    return period_start_dates[period]
