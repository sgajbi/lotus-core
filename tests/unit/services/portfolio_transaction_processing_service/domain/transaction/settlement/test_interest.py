"""Verify canonical INTEREST net and settlement-cash economics."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    calculate_interest_settlement_economics,
)


def _interest(**changes: object) -> BookedTransaction:
    values: dict[str, object] = {
        "transaction_id": "INTEREST-SETTLEMENT-001",
        "portfolio_id": "PORTFOLIO-001",
        "instrument_id": "BOND-USD-001",
        "security_id": "BOND-USD-001",
        "transaction_date": datetime(2026, 4, 10, 10, 30),
        "settlement_date": datetime(2026, 4, 12, 9, 0),
        "transaction_type": "INTEREST",
        "quantity": Decimal(0),
        "price": Decimal(0),
        "gross_transaction_amount": Decimal("120"),
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": Decimal("2"),
        "withholding_tax_amount": Decimal("10"),
        "other_interest_deductions_amount": Decimal("3"),
        "interest_direction": "INCOME",
    }
    values.update(changes)
    return BookedTransaction(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("direction", "fee", "expected_settlement"),
    [
        ("INCOME", "0", "107"),
        ("INCOME", "2", "105"),
        ("EXPENSE", "0", "107"),
        ("EXPENSE", "2", "109"),
    ],
)
def test_interest_settlement_applies_fee_once_by_cash_direction(
    direction: str,
    fee: str,
    expected_settlement: str,
) -> None:
    transaction = _interest(
        interest_direction=direction,
        trade_fee=Decimal(fee),
    )

    economics = calculate_interest_settlement_economics(transaction)

    assert economics.expected_net_interest_amount == Decimal("107")
    assert economics.net_interest_amount == Decimal("107")
    assert economics.transaction_fee_amount == Decimal(fee)
    assert economics.settlement_cash_amount == Decimal(expected_settlement)


@pytest.mark.parametrize("direction", ["INCOME", "EXPENSE"])
def test_explicit_and_derived_net_interest_are_settlement_invariant(direction: str) -> None:
    derived = _interest(interest_direction=direction)
    explicit = replace(derived, net_interest_amount=Decimal("107"))

    assert (
        calculate_interest_settlement_economics(explicit).settlement_cash_amount
        == calculate_interest_settlement_economics(derived).settlement_cash_amount
    )


def test_interest_settlement_uses_component_fee_total_as_authoritative() -> None:
    economics = calculate_interest_settlement_economics(
        _interest(
            trade_fee=Decimal("99"),
            brokerage=Decimal("1.25"),
            exchange_fee=Decimal("0.75"),
        )
    )

    assert economics.transaction_fee_amount == Decimal("2.00")
    assert economics.settlement_cash_amount == Decimal("105.00")


def test_interest_settlement_exposes_expected_net_for_reconciliation() -> None:
    economics = calculate_interest_settlement_economics(
        _interest(net_interest_amount=Decimal("108"))
    )

    assert economics.expected_net_interest_amount == Decimal("107")
    assert economics.net_interest_amount == Decimal("108")
    assert economics.settlement_cash_amount == Decimal("106")
