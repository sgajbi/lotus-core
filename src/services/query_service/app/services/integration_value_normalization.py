from __future__ import annotations

from decimal import Decimal
from typing import Any

from .decimal_amounts import decimal_or_none


def as_decimal(value: Any) -> Decimal:
    normalized_value = decimal_or_none(value)
    if normalized_value is None:
        raise ValueError("numeric value is required")
    return normalized_value


def as_optional_decimal(value: Any) -> Decimal | None:
    return decimal_or_none(value)


def control_code(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    normalized = str(value).strip().upper()
    return normalized or default


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
