"""Verify canonical redemption accrued-interest component construction."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CashflowClassification,
    CashflowRule,
    CashflowTiming,
    calculate_transaction_cashflow,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.redemption import (  # noqa: E501
    REDEMPTION_ACCRUED_INTEREST_COMPONENT,
    build_redemption_accrued_interest_component,
    is_generated_redemption_accrued_interest,
)


def _redemption() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="REDEMPTION-001",
        portfolio_id="PORTFOLIO-001",
        instrument_id="BOND-001",
        security_id="BOND-001",
        transaction_date=datetime(2026, 4, 10),
        settlement_date=datetime(2026, 4, 12),
        transaction_type="MATURITY_REDEMPTION",
        quantity=Decimal("100"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("10025"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("2"),
        accrued_interest_proceeds_local=Decimal("25"),
        external_cash_transaction_id="REDEMPTION-001-CASHLEG",
        economic_event_id="EVENT-001",
        linked_transaction_group_id="GROUP-001",
    )


def test_builds_linked_income_component_without_a_second_cash_leg() -> None:
    component = build_redemption_accrued_interest_component(
        replace(
            _redemption(),
            net_cost=Decimal("90"),
            net_cost_local=Decimal("90"),
            realized_gain_loss=Decimal("10"),
            allocated_cost_basis_local=Decimal("90"),
        )
    )

    assert component is not None
    assert component.transaction_id == "REDEMPTION-001-ACCRUED-INTEREST"
    assert component.transaction_type == "INTEREST"
    assert component.component_type == REDEMPTION_ACCRUED_INTEREST_COMPONENT
    assert component.gross_transaction_amount == Decimal("25")
    assert component.net_interest_amount == Decimal("25")
    assert component.cash_entry_mode is None
    assert component.external_cash_transaction_id == "REDEMPTION-001-CASHLEG"
    assert component.originating_transaction_id == "REDEMPTION-001"
    assert component.component_id == "REDEMPTION-001-ACCRUED-INTEREST:v1"
    assert component.net_cost is None
    assert component.net_cost_local is None
    assert component.realized_gain_loss is None
    assert component.allocated_cost_basis_local is None
    assert component.calculation_lineage is not None
    assert component.calculation_lineage.algorithm_id == "redemption-accrued-interest-component"
    assert is_generated_redemption_accrued_interest(component)


def test_omits_zero_interest_and_rejects_unlinked_positive_interest() -> None:
    assert (
        build_redemption_accrued_interest_component(
            replace(_redemption(), transaction_type="INTEREST")
        )
        is None
    )
    assert (
        build_redemption_accrued_interest_component(
            replace(_redemption(), accrued_interest_proceeds_local=Decimal(0))
        )
        is None
    )
    with pytest.raises(ValueError, match="linked settlement cash"):
        build_redemption_accrued_interest_component(
            replace(_redemption(), external_cash_transaction_id=None)
        )


def test_redemption_and_generated_interest_have_distinct_cashflow_classifications() -> None:
    redemption = _redemption()
    interest = build_redemption_accrued_interest_component(redemption)

    assert interest is not None
    principal_cashflow = calculate_transaction_cashflow(
        redemption,
        CashflowRule(
            classification=CashflowClassification.INVESTMENT_INFLOW,
            timing=CashflowTiming.EOD,
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )
    income_cashflow = calculate_transaction_cashflow(
        interest,
        CashflowRule(
            classification=CashflowClassification.INCOME,
            timing=CashflowTiming.EOD,
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )

    assert principal_cashflow.amount == Decimal("9998.0000000000")
    assert principal_cashflow.classification == "INVESTMENT_INFLOW"
    assert income_cashflow.amount == Decimal("25.0000000000")
    assert income_cashflow.classification == "INCOME"
    assert principal_cashflow.cashflow_date == income_cashflow.cashflow_date
    assert principal_cashflow.amount + income_cashflow.amount == Decimal("10023.0000000000")


def test_zero_superseding_interest_component_produces_zero_income_cashflow() -> None:
    component = build_redemption_accrued_interest_component(
        replace(_redemption(), accrued_interest_proceeds_local=Decimal(0)),
        include_zero=True,
    )

    assert component is not None
    cashflow = calculate_transaction_cashflow(
        component,
        CashflowRule(
            classification=CashflowClassification.INCOME,
            timing=CashflowTiming.EOD,
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )
    assert cashflow.amount == Decimal(0)
