from __future__ import annotations

from decimal import Decimal

POSITION_INCREASE_TRANSACTION_TYPES = {"BUY", "TRANSFER_IN"}
POSITION_DECREASE_TRANSACTION_TYPES = {"SELL", "TRANSFER_OUT"}


def transaction_quantity_effect_decimal(transaction_type: str | None, quantity) -> Decimal:
    normalized_type = str(transaction_type or "").upper()
    magnitude = Decimal(str(quantity or 0))
    if normalized_type in POSITION_INCREASE_TRANSACTION_TYPES:
        return magnitude
    if normalized_type in POSITION_DECREASE_TRANSACTION_TYPES:
        return -magnitude
    return Decimal(0)


def transaction_quantity_effect_float(transaction_type: str | None, quantity) -> float:
    return float(transaction_quantity_effect_decimal(transaction_type, quantity))
