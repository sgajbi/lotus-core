from __future__ import annotations

from decimal import Decimal
from typing import Any

ZERO = Decimal("0")


def decimal_or_zero(value: Any) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    normalized = str(value).strip()
    if not normalized:
        return ZERO
    return Decimal(normalized)
