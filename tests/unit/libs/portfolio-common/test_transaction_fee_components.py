from decimal import Decimal

import pytest
from portfolio_common.transaction_fee_components import resolve_transaction_trade_fee


def test_resolve_transaction_trade_fee_preserves_explicit_fee_without_components() -> None:
    assert resolve_transaction_trade_fee(Decimal("12.50"), {}) == Decimal("12.50")


def test_resolve_transaction_trade_fee_sums_present_components() -> None:
    assert resolve_transaction_trade_fee(
        trade_fee=Decimal("99"),
        fee_components={
            "brokerage": "1.25",
            "stamp_duty": Decimal("0.50"),
            "exchange_fee": None,
            "gst": "",
            "other_fees": "0.25",
        },
    ) == Decimal("2.00")


def test_resolve_transaction_trade_fee_rejects_negative_amounts() -> None:
    with pytest.raises(ValueError, match="brokerage must be greater than or equal to zero"):
        resolve_transaction_trade_fee(
            trade_fee=None,
            fee_components={"brokerage": Decimal("-0.01")},
        )


def test_resolve_transaction_trade_fee_rejects_invalid_amounts() -> None:
    with pytest.raises(ValueError, match="brokerage must be numeric"):
        resolve_transaction_trade_fee(
            trade_fee=None,
            fee_components={"brokerage": "not-a-fee"},
        )
