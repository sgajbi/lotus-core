"""Verify framework-neutral DIVIDEND and INTEREST validation behavior."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    DividendValidationReasonCode,
    InterestValidationReasonCode,
    validate_dividend_transaction,
    validate_interest_transaction,
)


def _income(transaction_type: str) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"{transaction_type.strip()}-VAL-001",
        transaction_type=transaction_type,
        portfolio_id="PORT-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 3, 5, 10, 0, 0),
        settlement_date=datetime(2026, 3, 7, 10, 0, 0),
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("123.45"),
        trade_fee=Decimal(0),
        trade_currency="USD",
        currency="USD",
        economic_event_id=f"EVT-{transaction_type.strip()}-001",
        linked_transaction_group_id=f"LTG-{transaction_type.strip()}-001",
        calculation_policy_id=f"{transaction_type.strip()}_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
    )


def test_income_validation_accepts_normalized_canonical_transactions() -> None:
    assert validate_dividend_transaction(_income(" dividend ")) == []
    assert (
        validate_interest_transaction(
            replace(_income(" interest "), interest_direction=" expense ")
        )
        == []
    )


def test_dividend_validation_reports_every_compatible_reason_code() -> None:
    transaction = replace(
        _income("OTHER"),
        settlement_date=None,
        quantity=Decimal(1),
        price=Decimal(1),
        gross_transaction_amount=Decimal(0),
        trade_currency="",
        currency="",
        economic_event_id=None,
        linked_transaction_group_id=None,
        calculation_policy_id=None,
        calculation_policy_version=None,
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=None,
    )

    issues = validate_dividend_transaction(transaction, strict_metadata=True)

    assert {issue.code for issue in issues} == set(DividendValidationReasonCode) - {
        DividendValidationReasonCode.INVALID_DATE_ORDER,
        DividendValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT,
    }


def test_interest_validation_reports_every_compatible_reason_code() -> None:
    transaction = replace(
        _income("OTHER"),
        settlement_date=None,
        quantity=Decimal(1),
        price=Decimal(1),
        gross_transaction_amount=Decimal(0),
        trade_currency="",
        currency="",
        economic_event_id=None,
        linked_transaction_group_id=None,
        calculation_policy_id=None,
        calculation_policy_version=None,
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=None,
        interest_direction="UNKNOWN",
        withholding_tax_amount=Decimal("-1"),
        other_interest_deductions_amount=Decimal("-1"),
        net_interest_amount=Decimal("5"),
    )

    issues = validate_interest_transaction(transaction, strict_metadata=True)

    assert {issue.code for issue in issues} == set(InterestValidationReasonCode) - {
        InterestValidationReasonCode.INVALID_DATE_ORDER,
        InterestValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT,
    }


def test_income_validation_rejects_booking_after_settlement() -> None:
    dividend = replace(
        _income("DIVIDEND"),
        transaction_date=datetime(2026, 3, 8, 10, 0, 0),
    )
    interest = replace(dividend, transaction_type="INTEREST")

    assert DividendValidationReasonCode.INVALID_DATE_ORDER in {
        issue.code for issue in validate_dividend_transaction(dividend)
    }
    assert InterestValidationReasonCode.INVALID_DATE_ORDER in {
        issue.code for issue in validate_interest_transaction(interest)
    }


def test_income_validation_requires_settlement_account_for_generated_cash() -> None:
    dividend = replace(_income("DIVIDEND"), cash_entry_mode="AUTO_GENERATE")
    interest = replace(_income("INTEREST"), cash_entry_mode="AUTO_GENERATE")

    assert DividendValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT in {
        issue.code for issue in validate_dividend_transaction(dividend)
    }
    assert InterestValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT in {
        issue.code for issue in validate_interest_transaction(interest)
    }


def test_interest_validation_accepts_reconciled_net_interest_amount() -> None:
    transaction = replace(
        _income("INTEREST"),
        trade_fee=Decimal("2.50"),
        withholding_tax_amount=Decimal("10"),
        other_interest_deductions_amount=Decimal("5"),
        net_interest_amount=Decimal("108.45"),
    )

    assert InterestValidationReasonCode.NET_INTEREST_RECONCILIATION_MISMATCH not in {
        issue.code for issue in validate_interest_transaction(transaction)
    }


def test_interest_validation_rejects_net_interest_reconciliation_mismatch() -> None:
    transaction = replace(
        _income("INTEREST"),
        trade_fee=Decimal("2.50"),
        withholding_tax_amount=Decimal("10"),
        other_interest_deductions_amount=Decimal("5"),
        net_interest_amount=Decimal("105.95"),
    )

    mismatch = next(
        issue
        for issue in validate_interest_transaction(transaction)
        if issue.code is InterestValidationReasonCode.NET_INTEREST_RECONCILIATION_MISMATCH
    )

    assert mismatch.code.value == "INTEREST_015_NET_RECONCILIATION_MISMATCH"
    assert mismatch.field == "net_interest_amount"
    assert mismatch.message.endswith("before transaction fees.")
