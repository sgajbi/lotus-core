"""Characterize framework-neutral transaction cashflow economics."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CashflowCalculationType,
    CashflowClassification,
    CashflowRule,
    CashflowTiming,
    calculate_transaction_cashflow,
)


def _booked_transaction(**changes: object) -> BookedTransaction:
    values: dict[str, object] = {
        "transaction_id": "TXN-CASHFLOW-001",
        "portfolio_id": "PORTFOLIO-001",
        "instrument_id": "INSTRUMENT-001",
        "security_id": "SECURITY-001",
        "transaction_date": datetime(2026, 4, 10, 10, 30),
        "transaction_type": "BUY",
        "quantity": Decimal("10"),
        "price": Decimal("100"),
        "gross_transaction_amount": Decimal("1000"),
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": Decimal("5.50"),
    }
    values.update(changes)
    return BookedTransaction(**values)  # type: ignore[arg-type]


def _rule(
    classification: CashflowClassification,
    *,
    timing: CashflowTiming = CashflowTiming.EOD,
    is_position_flow: bool = True,
    is_portfolio_flow: bool = False,
) -> CashflowRule:
    return CashflowRule(
        classification=classification.value,
        timing=timing.value,
        is_position_flow=is_position_flow,
        is_portfolio_flow=is_portfolio_flow,
    )


def test_buy_cashflow_includes_fees_and_uses_settlement_date() -> None:
    transaction = _booked_transaction(settlement_date=datetime(2026, 4, 12, 9, 0))

    cashflow = calculate_transaction_cashflow(
        transaction,
        _rule(CashflowClassification.INVESTMENT_OUTFLOW),
        epoch=7,
    )

    assert cashflow.cashflow_date == date(2026, 4, 12)
    assert cashflow.amount == Decimal("-1005.50")
    assert cashflow.currency == "USD"
    assert cashflow.calculation_type == CashflowCalculationType.NET.value
    assert cashflow.epoch == 7


@pytest.mark.parametrize("net_interest_amount", [None, Decimal("107")])
def test_interest_cashflow_is_invariant_to_explicit_net_interest(
    net_interest_amount: Decimal | None,
) -> None:
    transaction = _booked_transaction(
        transaction_type="INTEREST",
        gross_transaction_amount=Decimal("120"),
        trade_fee=Decimal("2"),
        withholding_tax_amount=Decimal("10"),
        other_interest_deductions_amount=Decimal("3"),
        net_interest_amount=net_interest_amount,
        interest_direction="EXPENSE",
    )

    cashflow = calculate_transaction_cashflow(
        transaction,
        _rule(CashflowClassification.EXPENSE),
    )

    assert cashflow.amount == Decimal("-109")


@pytest.mark.parametrize("net_interest_amount", [None, Decimal("107")])
def test_interest_income_cashflow_is_invariant_to_explicit_net_interest(
    net_interest_amount: Decimal | None,
) -> None:
    transaction = _booked_transaction(
        transaction_type="INTEREST",
        gross_transaction_amount=Decimal("120"),
        trade_fee=Decimal("2"),
        withholding_tax_amount=Decimal("10"),
        other_interest_deductions_amount=Decimal("3"),
        net_interest_amount=net_interest_amount,
        interest_direction="INCOME",
    )

    cashflow = calculate_transaction_cashflow(
        transaction,
        _rule(CashflowClassification.INCOME),
    )

    assert cashflow.amount == Decimal("105")


def test_synthetic_position_transfer_uses_source_owned_market_value() -> None:
    transaction = _booked_transaction(
        transaction_type="TRANSFER_IN",
        has_synthetic_flow=True,
        synthetic_flow_effective_date=date(2026, 4, 9),
        synthetic_flow_amount_local=Decimal("2500"),
        synthetic_flow_currency="SGD",
        synthetic_flow_classification="POSITION_TRANSFER_IN",
    )

    cashflow = calculate_transaction_cashflow(
        transaction,
        _rule(CashflowClassification.TRANSFER),
    )

    assert cashflow.cashflow_date == date(2026, 4, 9)
    assert cashflow.amount == Decimal("2500")
    assert cashflow.currency == "SGD"
    assert cashflow.calculation_type == CashflowCalculationType.MVT.value


def test_synthetic_transfer_rejects_sign_inconsistent_with_direction() -> None:
    transaction = _booked_transaction(
        transaction_type="TRANSFER_OUT",
        has_synthetic_flow=True,
        synthetic_flow_amount_local=Decimal("2500"),
        synthetic_flow_currency="SGD",
        synthetic_flow_classification="POSITION_TRANSFER_OUT",
    )

    with pytest.raises(
        ValueError,
        match="amount sign does not match its classification",
    ):
        calculate_transaction_cashflow(
            transaction,
            _rule(CashflowClassification.TRANSFER),
        )


def test_linked_corporate_action_settlement_is_not_double_counted_as_a_flow() -> None:
    transaction = _booked_transaction(
        transaction_type="ADJUSTMENT",
        originating_transaction_id="CA-CASH-001",
        originating_transaction_type="CASH_CONSIDERATION",
    )

    cashflow = calculate_transaction_cashflow(
        transaction,
        _rule(CashflowClassification.CORPORATE_ACTION_PROCEEDS),
    )

    assert cashflow.is_position_flow is False
    assert cashflow.is_portfolio_flow is False
