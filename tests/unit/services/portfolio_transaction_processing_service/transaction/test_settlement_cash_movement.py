"""Verify signed ordinary settlement cash policy and rejection boundaries."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    SettlementCashRejectionReasonCode,
    SettlementCashValidationError,
    calculate_settlement_cash_movement,
)


def _transaction(transaction_type: str, **changes: object) -> BookedTransaction:
    values: dict[str, object] = {
        "transaction_id": f"{transaction_type}-SETTLEMENT-001",
        "portfolio_id": "PORTFOLIO-001",
        "instrument_id": "INSTRUMENT-001",
        "security_id": "SECURITY-001",
        "transaction_date": datetime(2026, 4, 10, 10, 30),
        "settlement_date": datetime(2026, 4, 12, 9, 0),
        "transaction_type": transaction_type,
        "quantity": Decimal("0"),
        "price": Decimal("0"),
        "gross_transaction_amount": Decimal("100"),
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": Decimal("2"),
    }
    values.update(changes)
    return BookedTransaction(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("transaction_type", "signed_amount", "direction", "reason"),
    [
        ("BUY", Decimal("-102"), "OUTFLOW", "BUY_SETTLEMENT"),
        ("SELL", Decimal("98"), "INFLOW", "SELL_SETTLEMENT"),
        ("DIVIDEND", Decimal("98"), "INFLOW", "DIVIDEND_SETTLEMENT"),
    ],
)
def test_ordinary_settlement_cash_is_signed_from_portfolio_perspective(
    transaction_type: str,
    signed_amount: Decimal,
    direction: str,
    reason: str,
) -> None:
    movement = calculate_settlement_cash_movement(_transaction(transaction_type))

    assert movement.signed_amount == signed_amount
    assert movement.amount == abs(signed_amount)
    assert movement.movement_direction == direction
    assert movement.adjustment_reason == reason


def test_component_fees_take_precedence_over_aggregate_trade_fee() -> None:
    transaction = replace(
        _transaction("SELL"),
        brokerage=Decimal("1.25"),
        stamp_duty=Decimal("0.75"),
        exchange_fee=Decimal("0.50"),
        gst=Decimal("0.25"),
        other_fees=Decimal("0.25"),
        trade_fee=Decimal("99"),
    )

    movement = calculate_settlement_cash_movement(transaction)

    assert movement.fee_amount == Decimal("3.00")
    assert movement.signed_amount == Decimal("97.00")


@pytest.mark.parametrize(
    ("transaction_type", "fee", "reason_code"),
    [
        (
            "SELL",
            Decimal("100"),
            SettlementCashRejectionReasonCode.SELL_NON_POSITIVE_NET_SETTLEMENT,
        ),
        (
            "SELL",
            Decimal("100.0000000001"),
            SettlementCashRejectionReasonCode.SELL_NON_POSITIVE_NET_SETTLEMENT,
        ),
        (
            "DIVIDEND",
            Decimal("100"),
            SettlementCashRejectionReasonCode.DIVIDEND_NON_POSITIVE_NET_SETTLEMENT,
        ),
        (
            "DIVIDEND",
            Decimal("100.0000000001"),
            SettlementCashRejectionReasonCode.DIVIDEND_NON_POSITIVE_NET_SETTLEMENT,
        ),
    ],
)
def test_fee_equal_to_or_above_proceeds_is_rejected(
    transaction_type: str,
    fee: Decimal,
    reason_code: SettlementCashRejectionReasonCode,
) -> None:
    with pytest.raises(SettlementCashValidationError) as raised:
        calculate_settlement_cash_movement(_transaction(transaction_type, trade_fee=fee))

    assert raised.value.reason_code is reason_code
    assert raised.value.available_proceeds == Decimal("100")
    assert raised.value.fee_amount == fee
    assert raised.value.net_settlement_amount == Decimal("100") - fee


@pytest.mark.parametrize(
    ("direction", "expected_amount", "expected_reason"),
    [
        ("INCOME", Decimal("105"), "INTEREST_SETTLEMENT"),
        ("EXPENSE", Decimal("-109"), "INTEREST_CHARGE_SETTLEMENT"),
    ],
)
def test_interest_settlement_preserves_declared_direction(
    direction: str,
    expected_amount: Decimal,
    expected_reason: str,
) -> None:
    movement = calculate_settlement_cash_movement(
        _transaction(
            "INTEREST",
            gross_transaction_amount=Decimal("120"),
            withholding_tax_amount=Decimal("10"),
            other_interest_deductions_amount=Decimal("3"),
            net_interest_amount=Decimal("107"),
            interest_direction=direction,
        )
    )

    assert movement.signed_amount == expected_amount
    assert movement.adjustment_reason == expected_reason


@pytest.mark.parametrize("fee", [Decimal("8"), Decimal("8.0000000001")])
def test_interest_income_rejects_fee_that_consumes_net_interest(fee: Decimal) -> None:
    transaction = _transaction(
        "INTEREST",
        gross_transaction_amount=Decimal("10"),
        withholding_tax_amount=Decimal("2"),
        net_interest_amount=Decimal("8"),
        interest_direction="INCOME",
        trade_fee=fee,
    )

    with pytest.raises(SettlementCashValidationError) as raised:
        calculate_settlement_cash_movement(transaction)

    assert raised.value.reason_code is (
        SettlementCashRejectionReasonCode.INTEREST_NON_POSITIVE_NET_SETTLEMENT
    )
    assert raised.value.available_proceeds == Decimal("8")
    assert raised.value.net_settlement_amount == Decimal("8") - fee


def test_interest_rejects_explicit_net_that_does_not_reconcile() -> None:
    transaction = _transaction(
        "INTEREST",
        gross_transaction_amount=Decimal("10"),
        withholding_tax_amount=Decimal("2"),
        net_interest_amount=Decimal("100"),
        interest_direction="INCOME",
        trade_fee=Decimal("50"),
    )

    with pytest.raises(SettlementCashValidationError) as raised:
        calculate_settlement_cash_movement(transaction)

    assert raised.value.reason_code is (
        SettlementCashRejectionReasonCode.INTEREST_NET_RECONCILIATION_MISMATCH
    )
    assert raised.value.field == "net_interest_amount"
    assert raised.value.available_proceeds == Decimal("8")
    assert raised.value.fee_amount == Decimal("50")
    assert raised.value.net_settlement_amount == Decimal("-42")


def test_decimal_precision_is_not_quantized_by_settlement_policy() -> None:
    movement = calculate_settlement_cash_movement(
        _transaction(
            "DIVIDEND",
            gross_transaction_amount=Decimal("0.00000000000000000003"),
            trade_fee=Decimal("0.00000000000000000001"),
        )
    )

    assert movement.signed_amount == Decimal("0.00000000000000000002")
