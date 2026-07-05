from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

MAX_RAW_SERIES_WINDOW_DAYS: Final[int] = 3660


@dataclass(frozen=True, slots=True)
class CollectionWindowValidationError(ValueError):
    code: str
    message: str
    source_product: str
    start_date: date | None
    end_date: date | None
    max_window_days: int

    def __str__(self) -> str:
        return self.message


def validate_required_bounded_date_window(
    *,
    source_product: str,
    start_date: date | None,
    end_date: date | None,
    max_window_days: int = MAX_RAW_SERIES_WINDOW_DAYS,
) -> None:
    if start_date is None or end_date is None:
        raise CollectionWindowValidationError(
            code="COLLECTION_WINDOW_REQUIRED",
            message=(
                f"{source_product} requires start_date and end_date for bounded series reads."
            ),
            source_product=source_product,
            start_date=start_date,
            end_date=end_date,
            max_window_days=max_window_days,
        )

    if start_date > end_date:
        raise CollectionWindowValidationError(
            code="INVALID_DATE_WINDOW",
            message="start_date must be on or before end_date.",
            source_product=source_product,
            start_date=start_date,
            end_date=end_date,
            max_window_days=max_window_days,
        )

    window_days = (end_date - start_date).days + 1
    if window_days > max_window_days:
        raise CollectionWindowValidationError(
            code="COLLECTION_WINDOW_TOO_LARGE",
            message=(
                f"{source_product} date window is {window_days} days; maximum is "
                f"{max_window_days} days."
            ),
            source_product=source_product,
            start_date=start_date,
            end_date=end_date,
            max_window_days=max_window_days,
        )
