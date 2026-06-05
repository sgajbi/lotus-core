from __future__ import annotations

from datetime import date

import pytest

from src.services.query_service.app.dtos.analytics_input_dto import AnalyticsWindow
from src.services.query_service.app.services.analytics_windows import (
    AnalyticsWindowError,
    bounded_explicit_analytics_window,
    period_start_date,
    resolve_analytics_window,
)


def test_resolve_analytics_window_clamps_period_to_inception() -> None:
    window = resolve_analytics_window(
        as_of_date=date(2025, 1, 31),
        window=None,
        period="one_year",
        inception_date=date(2025, 1, 1),
    )

    assert window.start_date == date(2025, 1, 1)
    assert window.end_date == date(2025, 1, 31)


def test_resolve_analytics_window_bounds_explicit_end_date_to_as_of() -> None:
    window = resolve_analytics_window(
        as_of_date=date(2025, 1, 31),
        window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-02-28"),
        period=None,
        inception_date=date(2020, 1, 1),
    )

    assert window.start_date == date(2025, 1, 1)
    assert window.end_date == date(2025, 1, 31)


def test_bounded_explicit_analytics_window_rejects_inverted_window() -> None:
    with pytest.raises(AnalyticsWindowError, match="window.start_date"):
        bounded_explicit_analytics_window(
            window=AnalyticsWindow(start_date="2025-02-01", end_date="2025-02-28"),
            as_of_date=date(2025, 1, 31),
        )


def test_period_start_date_rejects_unsupported_period() -> None:
    with pytest.raises(AnalyticsWindowError, match="Unsupported period"):
        period_start_date(
            as_of_date=date(2025, 1, 31),
            period="bad",
            inception_date=date(2020, 1, 1),
        )
