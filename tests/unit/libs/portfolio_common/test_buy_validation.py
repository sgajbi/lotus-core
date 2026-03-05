from datetime import datetime
from decimal import Decimal

from portfolio_common.transaction_domain import (
    BuyCanonicalTransaction,
    BuyValidationReasonCode,
    validate_buy_transaction,
)


def _base_txn() -> BuyCanonicalTransaction:
    return BuyCanonicalTransaction(
        transaction_id="BUY_CANON_001",
        transaction_type="BUY",
        portfolio_id="PORT_001",
        instrument_id="SEC_UST_5Y",
        security_id="SEC_UST_5Y",
        transaction_date=datetime(2026, 3, 1, 10, 0, 0),
        settlement_date=datetime(2026, 3, 3, 10, 0, 0),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5"),
        trade_currency="USD",
        currency="USD",
    )


def test_validate_buy_transaction_happy_path() -> None:
    issues = validate_buy_transaction(_base_txn())
    assert issues == []


def test_validate_buy_transaction_detects_non_positive_quantity() -> None:
    txn = _base_txn().model_copy(update={"quantity": Decimal("0")})
    issues = validate_buy_transaction(txn)
    assert any(i.code == BuyValidationReasonCode.NON_POSITIVE_QUANTITY for i in issues)


def test_validate_buy_transaction_detects_invalid_date_order() -> None:
    txn = _base_txn().model_copy(update={"settlement_date": datetime(2026, 2, 28, 10, 0, 0)})
    issues = validate_buy_transaction(txn)
    assert any(i.code == BuyValidationReasonCode.INVALID_DATE_ORDER for i in issues)


def test_validate_buy_transaction_strict_metadata() -> None:
    issues = validate_buy_transaction(_base_txn(), strict_metadata=True)
    codes = {i.code for i in issues}
    assert BuyValidationReasonCode.MISSING_LINKAGE_IDENTIFIER in codes
    assert BuyValidationReasonCode.MISSING_POLICY_METADATA in codes
