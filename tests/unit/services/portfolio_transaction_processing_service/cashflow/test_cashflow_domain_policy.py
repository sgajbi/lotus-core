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
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    SettlementCashRejectionReasonCode,
    SettlementCashValidationError,
    build_generated_settlement_cash_leg,
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


@pytest.mark.parametrize(
    ("transaction_type", "classification", "fee", "expected_amount"),
    [
        ("SELL", CashflowClassification.INVESTMENT_INFLOW, "99", "1"),
        ("DIVIDEND", CashflowClassification.INCOME, "99", "1"),
        ("INTEREST", CashflowClassification.INCOME, "7", "1"),
    ],
)
def test_income_like_cashflow_preserves_positive_net_settlement(
    transaction_type: str,
    classification: CashflowClassification,
    fee: str,
    expected_amount: str,
) -> None:
    transaction = _booked_transaction(
        transaction_type=transaction_type,
        gross_transaction_amount=(
            Decimal("100") if transaction_type != "INTEREST" else Decimal("10")
        ),
        trade_fee=Decimal(fee),
        withholding_tax_amount=(Decimal("2") if transaction_type == "INTEREST" else None),
        interest_direction=("INCOME" if transaction_type == "INTEREST" else None),
    )

    cashflow = calculate_transaction_cashflow(transaction, _rule(classification))

    assert cashflow.amount == Decimal(expected_amount)


@pytest.mark.parametrize(
    ("transaction_type", "classification", "fee", "reason_code"),
    [
        (
            "SELL",
            CashflowClassification.INVESTMENT_INFLOW,
            "100",
            SettlementCashRejectionReasonCode.SELL_NON_POSITIVE_NET_SETTLEMENT,
        ),
        (
            "SELL",
            CashflowClassification.INVESTMENT_INFLOW,
            "100.01",
            SettlementCashRejectionReasonCode.SELL_NON_POSITIVE_NET_SETTLEMENT,
        ),
        (
            "DIVIDEND",
            CashflowClassification.INCOME,
            "100",
            SettlementCashRejectionReasonCode.DIVIDEND_NON_POSITIVE_NET_SETTLEMENT,
        ),
        (
            "DIVIDEND",
            CashflowClassification.INCOME,
            "100.01",
            SettlementCashRejectionReasonCode.DIVIDEND_NON_POSITIVE_NET_SETTLEMENT,
        ),
        (
            "INTEREST",
            CashflowClassification.INCOME,
            "8",
            SettlementCashRejectionReasonCode.INTEREST_NON_POSITIVE_NET_SETTLEMENT,
        ),
        (
            "INTEREST",
            CashflowClassification.INCOME,
            "8.01",
            SettlementCashRejectionReasonCode.INTEREST_NON_POSITIVE_NET_SETTLEMENT,
        ),
    ],
)
def test_cashflow_rejects_non_positive_income_like_settlement(
    transaction_type: str,
    classification: CashflowClassification,
    fee: str,
    reason_code: SettlementCashRejectionReasonCode,
) -> None:
    transaction = _booked_transaction(
        transaction_type=transaction_type,
        gross_transaction_amount=(
            Decimal("100") if transaction_type != "INTEREST" else Decimal("10")
        ),
        trade_fee=Decimal(fee),
        withholding_tax_amount=(Decimal("2") if transaction_type == "INTEREST" else None),
        interest_direction=("INCOME" if transaction_type == "INTEREST" else None),
    )

    with pytest.raises(SettlementCashValidationError) as raised:
        calculate_transaction_cashflow(transaction, _rule(classification))

    assert raised.value.reason_code is reason_code


@pytest.mark.parametrize(
    ("transaction_type", "classification", "changes"),
    [
        ("SELL", CashflowClassification.INVESTMENT_INFLOW, {}),
        (
            "DIVIDEND",
            CashflowClassification.INCOME,
            {"quantity": Decimal(0), "price": Decimal(0)},
        ),
        (
            "INTEREST",
            CashflowClassification.INCOME,
            {
                "quantity": Decimal(0),
                "price": Decimal(0),
                "net_interest_amount": Decimal("100"),
                "interest_direction": "INCOME",
            },
        ),
    ],
)
def test_product_and_generated_leg_cashflows_share_settlement_economics(
    transaction_type: str,
    classification: CashflowClassification,
    changes: dict[str, object],
) -> None:
    product_transaction = _booked_transaction(
        transaction_type=transaction_type,
        gross_transaction_amount=Decimal("100"),
        trade_fee=Decimal("2"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-001",
        settlement_cash_instrument_id="CASH-USD",
        **changes,
    )
    settlement_transaction = build_generated_settlement_cash_leg(product_transaction)

    product_cashflow = calculate_transaction_cashflow(
        product_transaction,
        _rule(classification),
    )
    settlement_cashflow = calculate_transaction_cashflow(
        settlement_transaction,
        _rule(CashflowClassification.TRANSFER),
    )

    assert product_cashflow.amount == Decimal("98")
    assert settlement_cashflow.amount == product_cashflow.amount
    assert settlement_transaction.movement_direction == "INFLOW"


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
