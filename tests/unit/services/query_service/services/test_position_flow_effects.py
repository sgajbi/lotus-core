from decimal import Decimal

import pytest
from portfolio_common.transaction_type_registry import TRANSACTION_TYPE_REGISTRY

from src.services.query_service.app.services.position_flow_effects import (
    CASH_POSITION_DECREASE_TRANSACTION_TYPES,
    CASH_POSITION_INCREASE_TRANSACTION_TYPES,
    POSITION_DECREASE_TRANSACTION_TYPES,
    POSITION_INCREASE_TRANSACTION_TYPES,
    transaction_quantity_effect_decimal,
)


class _StringCountedValue:
    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "amount", "expected"),
    [
        ("BUY", "10", None, Decimal("10")),
        (" buy ", "10", None, Decimal("10")),
        ("TRANSFER_IN", "3.5", None, Decimal("3.5")),
        ("MERGER_IN", "4", None, Decimal("4")),
        ("EXCHANGE_IN", "5", None, Decimal("5")),
        ("REPLACEMENT_IN", "6", None, Decimal("6")),
        ("SPIN_IN", "2", None, Decimal("2")),
        ("DEMERGER_IN", "3", None, Decimal("3")),
        ("SPLIT", "4", None, Decimal("4")),
        ("BONUS_ISSUE", "1.5", None, Decimal("1.5")),
        ("STOCK_DIVIDEND", "2.25", None, Decimal("2.25")),
        ("RIGHTS_ALLOCATE", "3", None, Decimal("3")),
        ("RIGHTS_SHARE_DELIVERY", "4", None, Decimal("4")),
        ("SELL", "7", None, Decimal("-7")),
        (" sell ", "7", None, Decimal("-7")),
        ("CASH_IN_LIEU", "0.5", None, Decimal("-0.5")),
        ("TRANSFER_OUT", "2", None, Decimal("-2")),
        ("MERGER_OUT", "1", None, Decimal("-1")),
        ("EXCHANGE_OUT", "2", None, Decimal("-2")),
        ("REPLACEMENT_OUT", "3", None, Decimal("-3")),
        ("SPIN_OFF", "1", None, Decimal("-1")),
        ("DEMERGER_OUT", "2", None, Decimal("-2")),
        ("REVERSE_SPLIT", "1.5", None, Decimal("-1.5")),
        ("CONSOLIDATION", "2", None, Decimal("-2")),
        ("RIGHTS_SUBSCRIBE", "3", None, Decimal("-3")),
        ("RIGHTS_OVERSUBSCRIBE", "1", None, Decimal("-1")),
        ("RIGHTS_SELL", "2", None, Decimal("-2")),
        ("RIGHTS_EXPIRE", "1", None, Decimal("-1")),
        ("DEPOSIT", "5", "7", Decimal("7")),
        (" deposit ", "5", "7", Decimal("7")),
        ("WITHDRAWAL", "5", "7", Decimal("-7")),
        ("FEE", "1", "7", Decimal("-7")),
        ("TAX", "1", "7", Decimal("-7")),
        ("UNKNOWN", "9", None, Decimal("0")),
    ],
)
def test_transaction_quantity_effect_decimal(transaction_type, quantity, amount, expected):
    assert transaction_quantity_effect_decimal(transaction_type, quantity, amount) == expected


def test_cash_position_effect_does_not_convert_unused_quantity() -> None:
    quantity = _StringCountedValue("999")
    amount = _StringCountedValue("7")

    effect = transaction_quantity_effect_decimal("DEPOSIT", quantity, amount)

    assert effect == Decimal("7")
    assert quantity.string_call_count == 0
    assert amount.string_call_count == 1


def test_unknown_position_effect_does_not_convert_unused_values() -> None:
    quantity = _StringCountedValue("999")
    amount = _StringCountedValue("7")

    effect = transaction_quantity_effect_decimal("UNKNOWN", quantity, amount)

    assert effect == Decimal("0")
    assert quantity.string_call_count == 0
    assert amount.string_call_count == 0


def test_position_flow_effect_sets_are_registry_derived() -> None:
    production_position_effects = {
        position_effect: {
            code
            for code, definition in TRANSACTION_TYPE_REGISTRY.items()
            if definition.production_booking_allowed
            and definition.position_effect == position_effect
        }
        for position_effect in {
            "increase",
            "decrease",
            "cash_increase",
            "cash_decrease",
        }
    }

    assert POSITION_INCREASE_TRANSACTION_TYPES == production_position_effects["increase"]
    assert POSITION_DECREASE_TRANSACTION_TYPES == production_position_effects["decrease"]
    assert CASH_POSITION_INCREASE_TRANSACTION_TYPES == production_position_effects["cash_increase"]
    assert CASH_POSITION_DECREASE_TRANSACTION_TYPES == production_position_effects["cash_decrease"]
