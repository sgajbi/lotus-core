from decimal import Decimal

import pytest

from src.services.query_service.app.services.position_flow_effects import (
    transaction_quantity_effect_decimal,
)


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "amount", "expected"),
    [
        ("BUY", "10", None, Decimal("10")),
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
        ("WITHDRAWAL", "5", "7", Decimal("-7")),
        ("FEE", "1", "7", Decimal("-7")),
        ("TAX", "1", "7", Decimal("-7")),
        ("UNKNOWN", "9", None, Decimal("0")),
    ],
)
def test_transaction_quantity_effect_decimal(transaction_type, quantity, amount, expected):
    assert transaction_quantity_effect_decimal(transaction_type, quantity, amount) == expected

