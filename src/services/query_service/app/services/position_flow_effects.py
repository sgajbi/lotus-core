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

def transaction_quantity_effect_decimal(
    transaction_type: str | None, quantity, amount=None
) -> Decimal:
    normalized_type = str(transaction_type or "").upper()
    magnitude = Decimal(str(quantity or 0))
    if normalized_type in POSITION_INCREASE_TRANSACTION_TYPES:
        return magnitude
    if normalized_type in POSITION_DECREASE_TRANSACTION_TYPES:
        return -magnitude
    if normalized_type in CASH_POSITION_INCREASE_TRANSACTION_TYPES:
        return abs(Decimal(str(amount or 0)))
    if normalized_type in CASH_POSITION_DECREASE_TRANSACTION_TYPES:
        return -abs(Decimal(str(amount or 0)))
    return Decimal(0)
