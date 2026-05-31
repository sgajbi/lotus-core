from __future__ import annotations

from decimal import Decimal
from typing import Any


def as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def control_code(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    normalized = str(value).strip().upper()
    return normalized or default
