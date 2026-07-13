"""Generic position-quantity effects for proposed transaction changes."""

from decimal import Decimal
from typing import cast

from portfolio_common.domain.decimal_amount import decimal_or_zero
from portfolio_common.domain.transaction.type_registry import (
    production_transaction_types_for_position_effects,
)

POSITION_INCREASE_TRANSACTION_TYPES = production_transaction_types_for_position_effects("increase")
POSITION_DECREASE_TRANSACTION_TYPES = production_transaction_types_for_position_effects("decrease")
CASH_POSITION_INCREASE_TRANSACTION_TYPES = production_transaction_types_for_position_effects(
    "cash_increase"
)
CASH_POSITION_DECREASE_TRANSACTION_TYPES = production_transaction_types_for_position_effects(
    "cash_decrease"
)


def transaction_quantity_effect(
    *,
    transaction_type: str | None,
    quantity: object,
    amount: object = None,
) -> Decimal:
    """Return the signed position quantity effect for a proposed transaction."""

    normalized_type = str(transaction_type or "").strip().upper()
    if normalized_type in POSITION_INCREASE_TRANSACTION_TYPES:
        return cast(Decimal, decimal_or_zero(quantity))
    if normalized_type in POSITION_DECREASE_TRANSACTION_TYPES:
        return cast(Decimal, -decimal_or_zero(quantity))
    if normalized_type in CASH_POSITION_INCREASE_TRANSACTION_TYPES:
        return cast(Decimal, abs(decimal_or_zero(amount)))
    if normalized_type in CASH_POSITION_DECREASE_TRANSACTION_TYPES:
        return cast(Decimal, -abs(decimal_or_zero(amount)))
    return Decimal(0)
