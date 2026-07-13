"""Verify framework-neutral BUY and SELL validation reason-code behavior."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    BuyValidationReasonCode,
    SellValidationReasonCode,
    validate_buy_transaction,
    validate_sell_transaction,
)


def _trade(transaction_type: str) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"{transaction_type}-CANON-001",
        transaction_type=transaction_type,
        portfolio_id="PORT-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 3, 1, 10, 0, 0),
        settlement_date=datetime(2026, 3, 3, 10, 0, 0),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5"),
        trade_currency="USD",
        currency="USD",
    )


@pytest.mark.parametrize(
    ("transaction_type", "validator"),
    [
        (" buy ", validate_buy_transaction),
        (" sell ", validate_sell_transaction),
    ],
)
def test_trade_validation_accepts_normalized_canonical_transaction(
    transaction_type: str,
    validator: object,
) -> None:
    assert callable(validator)
    assert validator(_trade(transaction_type)) == []


@pytest.mark.parametrize(
    ("transaction_type", "validator", "expected_codes"),
    [
        (
            "BUY",
            validate_buy_transaction,
            set(BuyValidationReasonCode),
        ),
        (
            "SELL",
            validate_sell_transaction,
            set(SellValidationReasonCode),
        ),
    ],
)
def test_trade_validation_reports_every_reason_code(
    transaction_type: str,
    validator: object,
    expected_codes: set[StrEnum],
) -> None:
    assert callable(validator)
    transaction = replace(
        _trade("OTHER"),
        transaction_type="OTHER",
        settlement_date=None,
        quantity=Decimal(0),
        gross_transaction_amount=Decimal(0),
        trade_currency="",
        currency="",
        economic_event_id=None,
        linked_transaction_group_id=None,
        calculation_policy_id=None,
        calculation_policy_version=None,
    )

    issues = validator(transaction, strict_metadata=True)

    assert {issue.code for issue in issues} == expected_codes - {
        (
            BuyValidationReasonCode.INVALID_DATE_ORDER
            if transaction_type == "BUY"
            else SellValidationReasonCode.INVALID_DATE_ORDER
        ),
        *(
            {SellValidationReasonCode.NON_POSITIVE_NET_SETTLEMENT}
            if transaction_type == "SELL"
            else set()
        ),
    }


@pytest.mark.parametrize(
    ("validator", "reason_code"),
    [
        (validate_buy_transaction, BuyValidationReasonCode.INVALID_DATE_ORDER),
        (validate_sell_transaction, SellValidationReasonCode.INVALID_DATE_ORDER),
    ],
)
def test_trade_validation_rejects_trade_after_settlement(
    validator: object,
    reason_code: StrEnum,
) -> None:
    assert callable(validator)
    transaction = replace(
        _trade("BUY"),
        transaction_date=datetime(2026, 3, 4, 10, 0, 0),
    )

    assert reason_code in {issue.code for issue in validator(transaction)}


@pytest.mark.parametrize("fee", [Decimal("1000"), Decimal("1000.01")])
def test_sell_validation_rejects_non_positive_net_settlement(fee: Decimal) -> None:
    issues = validate_sell_transaction(replace(_trade("SELL"), trade_fee=fee))

    settlement_issue = next(
        issue
        for issue in issues
        if issue.code is SellValidationReasonCode.NON_POSITIVE_NET_SETTLEMENT
    )
    assert settlement_issue.field == "trade_fee"
