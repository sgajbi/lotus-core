"""SQL normalization and date-boundary helpers for operations queries."""

from datetime import date, datetime, time, timedelta
from typing import Any

from portfolio_common.domain.currency import normalize_currency_code
from sqlalchemy import func


def currency_code_sql_expr(currency_code_column: Any) -> Any:
    """Normalize a persisted currency expression for tolerant source reads."""

    return func.upper(func.trim(currency_code_column))


def start_of_next_day(value: date) -> datetime:
    """Return the exclusive UTC-naive SQL boundary after a business date."""

    return datetime.combine(value + timedelta(days=1), time.min)


__all__ = ["currency_code_sql_expr", "normalize_currency_code", "start_of_next_day"]
