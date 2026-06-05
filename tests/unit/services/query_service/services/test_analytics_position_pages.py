from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.analytics_input_dto import (
    AnalyticsWindow,
    PositionAnalyticsFilters,
    PositionAnalyticsTimeseriesRequest,
    PositionDimensionFilter,
)
from src.services.query_service.app.services.analytics_position_pages import (
    position_dimension_filters,
    position_page_scope,
    previous_position_eod_by_security,
)


def test_position_page_scope_sorts_dates_and_normalizes_security_ids() -> None:
    scope = position_page_scope(
        rows_page=[
            SimpleNamespace(valuation_date=date(2025, 1, 31), security_id="SEC_B"),
            SimpleNamespace(valuation_date=date(2025, 1, 30), security_id="SEC_A"),
            SimpleNamespace(valuation_date=date(2025, 1, 31), security_id="SEC_A"),
        ],
        fallback_start_date=date(2025, 1, 1),
    )

    assert scope.page_dates == [date(2025, 1, 30), date(2025, 1, 31)]
    assert scope.page_start_date == date(2025, 1, 30)
    assert scope.page_end_date == date(2025, 1, 31)
    assert scope.first_page_date == date(2025, 1, 30)
    assert scope.security_ids == ["SEC_A", "SEC_B"]


def test_previous_position_eod_by_security_keeps_only_prior_day_rows() -> None:
    result = previous_position_eod_by_security(
        previous_rows=[
            SimpleNamespace(
                valuation_date=date(2025, 1, 30),
                security_id="SEC_A",
                eod_market_value=Decimal("100"),
            ),
            SimpleNamespace(
                valuation_date=date(2025, 1, 29),
                security_id="SEC_B",
                eod_market_value=Decimal("200"),
            ),
        ],
        first_page_date=date(2025, 1, 31),
    )

    assert result == {"SEC_A": Decimal("100")}


def test_position_dimension_filters_returns_dimension_value_sets() -> None:
    request = PositionAnalyticsTimeseriesRequest(
        as_of_date="2025-12-31",
        window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
        filters=PositionAnalyticsFilters(
            dimension_filters=[
                PositionDimensionFilter(dimension="sector", values=["Technology", "Healthcare"]),
                PositionDimensionFilter(dimension="country", values=["US"]),
            ]
        ),
    )

    assert position_dimension_filters(request) == {
        "sector": {"Technology", "Healthcare"},
        "country": {"US"},
    }
