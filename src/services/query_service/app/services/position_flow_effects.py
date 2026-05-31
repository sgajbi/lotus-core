from __future__ import annotations

from decimal import Decimal

POSITION_INCREASE_TRANSACTION_TYPES = {
    "BUY",
    "TRANSFER_IN",
    "MERGER_IN",
    "EXCHANGE_IN",
    "REPLACEMENT_IN",
    "SPIN_IN",
    "DEMERGER_IN",
    "SPLIT",
    "BONUS_ISSUE",
    "STOCK_DIVIDEND",
    "RIGHTS_ALLOCATE",
    "RIGHTS_SHARE_DELIVERY",
}
POSITION_DECREASE_TRANSACTION_TYPES = {
    "SELL",
    "CASH_IN_LIEU",
    "TRANSFER_OUT",
    "MERGER_OUT",
    "EXCHANGE_OUT",
    "REPLACEMENT_OUT",
    "SPIN_OFF",
    "DEMERGER_OUT",
    "REVERSE_SPLIT",
    "CONSOLIDATION",
    "RIGHTS_SUBSCRIBE",
    "RIGHTS_OVERSUBSCRIBE",
    "RIGHTS_SELL",
    "RIGHTS_EXPIRE",
}
CASH_POSITION_INCREASE_TRANSACTION_TYPES = {"DEPOSIT"}
CASH_POSITION_DECREASE_TRANSACTION_TYPES = {"WITHDRAWAL", "FEE", "TAX"}


def _decimal_or_zero(value) -> Decimal:
    return Decimal(str(value or 0))


def transaction_quantity_effect_decimal(
    transaction_type: str | None, quantity, amount=None
) -> Decimal:
    normalized_type = str(transaction_type or "").strip().upper()
    if normalized_type in POSITION_INCREASE_TRANSACTION_TYPES:
        magnitude = _decimal_or_zero(quantity)
        return magnitude
    if normalized_type in POSITION_DECREASE_TRANSACTION_TYPES:
        magnitude = _decimal_or_zero(quantity)
        return -magnitude
    if normalized_type in CASH_POSITION_INCREASE_TRANSACTION_TYPES:
        return abs(_decimal_or_zero(amount))
    if normalized_type in CASH_POSITION_DECREASE_TRANSACTION_TYPES:
        return -abs(_decimal_or_zero(amount))
    return Decimal(0)
