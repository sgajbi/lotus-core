from datetime import date

import pytest

from src.services.query_service.app.application.collection_window_policy import (
    CollectionWindowValidationError,
    validate_required_bounded_date_window,
)


def test_required_bounded_date_window_accepts_ten_year_window() -> None:
    validate_required_bounded_date_window(
        source_product="MarketPriceSeries",
        start_date=date(2020, 1, 1),
        end_date=date(2030, 1, 7),
    )


def test_required_bounded_date_window_rejects_missing_bound() -> None:
    with pytest.raises(CollectionWindowValidationError) as exc_info:
        validate_required_bounded_date_window(
            source_product="FxRateSeries",
            start_date=date(2026, 1, 1),
            end_date=None,
        )

    assert exc_info.value.code == "COLLECTION_WINDOW_REQUIRED"
    assert exc_info.value.source_product == "FxRateSeries"


def test_required_bounded_date_window_rejects_reversed_window() -> None:
    with pytest.raises(CollectionWindowValidationError) as exc_info:
        validate_required_bounded_date_window(
            source_product="PositionHistorySeries",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
        )

    assert exc_info.value.code == "INVALID_DATE_WINDOW"


def test_required_bounded_date_window_rejects_oversized_window() -> None:
    with pytest.raises(CollectionWindowValidationError) as exc_info:
        validate_required_bounded_date_window(
            source_product="MarketPriceSeries",
            start_date=date(2020, 1, 1),
            end_date=date(2030, 1, 8),
        )

    assert exc_info.value.code == "COLLECTION_WINDOW_TOO_LARGE"
    assert exc_info.value.max_window_days == 3660
