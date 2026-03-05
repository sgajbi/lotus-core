from datetime import datetime
from decimal import Decimal

from portfolio_common.transaction_domain import (
    SellCanonicalTransaction,
    SellValidationReasonCode,
    validate_sell_transaction,
)


def _base_txn() -> SellCanonicalTransaction:
    return SellCanonicalTransaction(
        transaction_id="SELL_CANON_001",
        transaction_type="SELL",
        portfolio_id="PORT_001",
        instrument_id="SEC_EQ_ABC",
        security_id="SEC_EQ_ABC",
        transaction_date=datetime(2026, 3, 4, 10, 0, 0),
        settlement_date=datetime(2026, 3, 6, 10, 0, 0),
        quantity=Decimal("10"),
        price=Decimal("101.25"),
        gross_transaction_amount=Decimal("1012.5"),
        trade_fee=Decimal("5"),
        trade_currency="USD",
        currency="USD",
    )


def test_validate_sell_transaction_happy_path() -> None:
    issues = validate_sell_transaction(_base_txn())
    assert issues == []


def test_validate_sell_transaction_detects_non_positive_quantity() -> None:
    txn = _base_txn().model_copy(update={"quantity": Decimal("0")})
    issues = validate_sell_transaction(txn)
    assert any(i.code == SellValidationReasonCode.NON_POSITIVE_QUANTITY for i in issues)


def test_validate_sell_transaction_detects_invalid_date_order() -> None:
    txn = _base_txn().model_copy(update={"settlement_date": datetime(2026, 3, 3, 10, 0, 0)})
    issues = validate_sell_transaction(txn)
    assert any(i.code == SellValidationReasonCode.INVALID_DATE_ORDER for i in issues)


def test_validate_sell_transaction_strict_metadata() -> None:
    issues = validate_sell_transaction(_base_txn(), strict_metadata=True)
    codes = {i.code for i in issues}
    assert SellValidationReasonCode.MISSING_LINKAGE_IDENTIFIER in codes
    assert SellValidationReasonCode.MISSING_POLICY_METADATA in codes
