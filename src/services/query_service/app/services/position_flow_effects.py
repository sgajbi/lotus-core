from __future__ import annotations

from decimal import Decimal
from typing import cast

from portfolio_common.transaction_type_registry import TRANSACTION_TYPE_REGISTRY

from .decimal_amounts import decimal_or_zero


def _transaction_types_with_position_effect(position_effect: str) -> frozenset[str]:
    return frozenset(
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed and definition.position_effect == position_effect
    )


POSITION_INCREASE_TRANSACTION_TYPES = _transaction_types_with_position_effect("increase")
POSITION_DECREASE_TRANSACTION_TYPES = _transaction_types_with_position_effect("decrease")
CASH_POSITION_INCREASE_TRANSACTION_TYPES = _transaction_types_with_position_effect("cash_increase")
CASH_POSITION_DECREASE_TRANSACTION_TYPES = _transaction_types_with_position_effect("cash_decrease")


def transaction_quantity_effect_decimal(
    transaction_type: str | None, quantity, amount=None
) -> Decimal:
    normalized_type = str(transaction_type or "").strip().upper()
    if normalized_type in POSITION_INCREASE_TRANSACTION_TYPES:
        magnitude = decimal_or_zero(quantity)
        return cast(Decimal, magnitude)
    if normalized_type in POSITION_DECREASE_TRANSACTION_TYPES:
        magnitude = decimal_or_zero(quantity)
        return cast(Decimal, -magnitude)
    if normalized_type in CASH_POSITION_INCREASE_TRANSACTION_TYPES:
        return cast(Decimal, abs(decimal_or_zero(amount)))
    if normalized_type in CASH_POSITION_DECREASE_TRANSACTION_TYPES:
        return cast(Decimal, -abs(decimal_or_zero(amount)))
    return Decimal(0)
