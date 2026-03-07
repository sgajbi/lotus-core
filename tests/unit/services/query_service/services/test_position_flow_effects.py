from decimal import Decimal

import pytest

from src.services.query_service.app.services.position_flow_effects import (
    transaction_quantity_effect_decimal,
    transaction_quantity_effect_float,
)


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "expected"),
    [
        ("BUY", "10", Decimal("10")),
        ("TRANSFER_IN", "3.5", Decimal("3.5")),
        ("MERGER_IN", "4", Decimal("4")),
        ("EXCHANGE_IN", "5", Decimal("5")),
        ("REPLACEMENT_IN", "6", Decimal("6")),
        ("SPIN_IN", "2", Decimal("2")),
        ("DEMERGER_IN", "3", Decimal("3")),
        ("SELL", "7", Decimal("-7")),
        ("CASH_IN_LIEU", "0.5", Decimal("-0.5")),
        ("TRANSFER_OUT", "2", Decimal("-2")),
        ("MERGER_OUT", "1", Decimal("-1")),
        ("EXCHANGE_OUT", "2", Decimal("-2")),
        ("REPLACEMENT_OUT", "3", Decimal("-3")),
        ("SPIN_OFF", "1", Decimal("-1")),
        ("DEMERGER_OUT", "2", Decimal("-2")),
        ("DEPOSIT", "5", Decimal("0")),
        ("WITHDRAWAL", "5", Decimal("0")),
        ("FEE", "1", Decimal("0")),
        ("TAX", "1", Decimal("0")),
        ("UNKNOWN", "9", Decimal("0")),
    ],
)
def test_transaction_quantity_effect_decimal(transaction_type, quantity, expected):
    assert transaction_quantity_effect_decimal(transaction_type, quantity) == expected


def test_transaction_quantity_effect_float() -> None:
    assert transaction_quantity_effect_float("BUY", 2) == 2.0
    assert transaction_quantity_effect_float("SELL", 2) == -2.0
    assert transaction_quantity_effect_float("DEPOSIT", 2) == 0.0
