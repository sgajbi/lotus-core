from __future__ import annotations

from decimal import Decimal


def decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    normalized = str(value).strip()
    if not normalized:
        return None
    return Decimal(normalized)


def required_decimal(value: object, *, field_name: str) -> Decimal:
    resolved_value = decimal_or_none(value)
    if resolved_value is None:
        raise ValueError(f"{field_name} is required")
    return resolved_value
