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
        ("SELL", "7", Decimal("-7")),
        ("TRANSFER_OUT", "2", Decimal("-2")),
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
