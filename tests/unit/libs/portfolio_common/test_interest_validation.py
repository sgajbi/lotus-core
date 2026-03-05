from datetime import datetime
from decimal import Decimal

from portfolio_common.transaction_domain import (
    InterestCanonicalTransaction,
    InterestValidationReasonCode,
    validate_interest_transaction,
)


def _base_txn() -> InterestCanonicalTransaction:
    return InterestCanonicalTransaction(
        transaction_id="INT_VAL_001",
        transaction_type="INTEREST",
        portfolio_id="PORT_001",
        instrument_id="BOND_10Y_USD",
        security_id="BOND_10Y_USD",
        transaction_date=datetime(2026, 3, 5, 10, 0, 0),
        settlement_date=datetime(2026, 3, 7, 10, 0, 0),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("123.45"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        economic_event_id="EVT-INT-001",
        linked_transaction_group_id="LTG-INT-001",
        calculation_policy_id="INTEREST_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
    )


def test_validate_interest_transaction_happy_path() -> None:
    issues = validate_interest_transaction(_base_txn())
    assert issues == []


def test_validate_interest_transaction_detects_non_zero_quantity() -> None:
    txn = _base_txn().model_copy(update={"quantity": Decimal("1")})
    issues = validate_interest_transaction(txn)
    assert any(i.code == InterestValidationReasonCode.NON_ZERO_QUANTITY for i in issues)


def test_validate_interest_transaction_detects_non_zero_price() -> None:
    txn = _base_txn().model_copy(update={"price": Decimal("10")})
    issues = validate_interest_transaction(txn)
    assert any(i.code == InterestValidationReasonCode.NON_ZERO_PRICE for i in issues)


def test_validate_interest_transaction_detects_non_positive_gross_amount() -> None:
    txn = _base_txn().model_copy(update={"gross_transaction_amount": Decimal("0")})
    issues = validate_interest_transaction(txn)
    assert any(i.code == InterestValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT for i in issues)


def test_validate_interest_transaction_rejects_unknown_direction() -> None:
    txn = _base_txn().model_copy(update={"interest_direction": "UNKNOWN"})
    issues = validate_interest_transaction(txn)
    assert any(i.code == InterestValidationReasonCode.INVALID_INTEREST_DIRECTION for i in issues)


def test_validate_interest_transaction_accepts_expense_direction() -> None:
    txn = _base_txn().model_copy(update={"interest_direction": "EXPENSE"})
    issues = validate_interest_transaction(txn)
    assert not any(
        i.code == InterestValidationReasonCode.INVALID_INTEREST_DIRECTION for i in issues
    )


def test_validate_interest_transaction_rejects_negative_withholding_tax() -> None:
    txn = _base_txn().model_copy(update={"withholding_tax_amount": Decimal("-1")})
    issues = validate_interest_transaction(txn)
    assert any(i.code == InterestValidationReasonCode.NEGATIVE_WITHHOLDING_TAX for i in issues)


def test_validate_interest_transaction_rejects_negative_other_deductions() -> None:
    txn = _base_txn().model_copy(update={"other_interest_deductions_amount": Decimal("-1")})
    issues = validate_interest_transaction(txn)
    assert any(i.code == InterestValidationReasonCode.NEGATIVE_OTHER_DEDUCTIONS for i in issues)


def test_validate_interest_transaction_rejects_net_reconciliation_mismatch() -> None:
    txn = _base_txn().model_copy(
        update={
            "withholding_tax_amount": Decimal("10"),
            "other_interest_deductions_amount": Decimal("5"),
            "net_interest_amount": Decimal("120"),
        }
    )
    issues = validate_interest_transaction(txn)
    assert any(
        i.code == InterestValidationReasonCode.NET_INTEREST_RECONCILIATION_MISMATCH for i in issues
    )


def test_validate_interest_transaction_accepts_reconciled_net_interest_amount() -> None:
    txn = _base_txn().model_copy(
        update={
            "withholding_tax_amount": Decimal("10"),
            "other_interest_deductions_amount": Decimal("5"),
            "net_interest_amount": Decimal("108.45"),
        }
    )
    issues = validate_interest_transaction(txn)
    assert not any(
        i.code == InterestValidationReasonCode.NET_INTEREST_RECONCILIATION_MISMATCH for i in issues
    )


def test_validate_interest_transaction_rejects_unknown_direction() -> None:
    txn = _base_txn().model_copy(update={"interest_direction": "UNKNOWN"})
    issues = validate_interest_transaction(txn)
    assert any(
        i.code == InterestValidationReasonCode.INVALID_INTEREST_DIRECTION
        for i in issues
    )


def test_validate_interest_transaction_accepts_expense_direction() -> None:
    txn = _base_txn().model_copy(update={"interest_direction": "EXPENSE"})
    issues = validate_interest_transaction(txn)
    assert not any(
        i.code == InterestValidationReasonCode.INVALID_INTEREST_DIRECTION
        for i in issues
    )


def test_validate_interest_transaction_detects_invalid_date_order() -> None:
    txn = _base_txn().model_copy(update={"transaction_date": datetime(2026, 3, 8, 10, 0, 0)})
    issues = validate_interest_transaction(txn)
    assert any(i.code == InterestValidationReasonCode.INVALID_DATE_ORDER for i in issues)


def test_validate_interest_transaction_strict_metadata() -> None:
    txn = _base_txn().model_copy(
        update={
            "economic_event_id": None,
            "linked_transaction_group_id": None,
            "calculation_policy_id": None,
            "calculation_policy_version": None,
        }
    )
    issues = validate_interest_transaction(txn, strict_metadata=True)
    assert any(i.code == InterestValidationReasonCode.MISSING_LINKAGE_IDENTIFIER for i in issues)
    assert any(i.code == InterestValidationReasonCode.MISSING_POLICY_METADATA for i in issues)


def test_validate_interest_transaction_requires_external_cash_link_for_external_mode() -> None:
    txn = _base_txn().model_copy(
        update={
            "cash_entry_mode": "UPSTREAM_PROVIDED",
            "external_cash_transaction_id": None,
        }
    )
    issues = validate_interest_transaction(txn)
    assert any(i.code == InterestValidationReasonCode.MISSING_EXTERNAL_CASH_LINK for i in issues)


def test_validate_interest_transaction_requires_settlement_cash_account_for_auto_mode() -> None:
    txn = _base_txn().model_copy(
        update={
            "cash_entry_mode": "AUTO_GENERATE",
            "settlement_cash_account_id": None,
        }
    )
    issues = validate_interest_transaction(txn)
    assert any(
        i.code == InterestValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT for i in issues
    )
