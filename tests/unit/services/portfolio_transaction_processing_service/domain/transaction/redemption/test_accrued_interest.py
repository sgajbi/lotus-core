"""Verify canonical redemption accrued-interest component construction."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import build_calculation_lineage

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CashflowCalculationContext,
    CashflowClassification,
    CashflowRule,
    CashflowTiming,
    calculate_transaction_cashflow,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    SettlementCashValidationError,
    should_generate_settlement_cash_leg,
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
        tenant_id="tenant-test",
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
    assert component.tenant_id == "tenant-test"
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
            replace(_redemption(), accrued_interest_proceeds_local=None)
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


def test_builds_positive_interest_evidence_for_zero_net_settlement_without_cash_leg() -> None:
    redemption = replace(
        _redemption(),
        quantity=Decimal("1"),
        price=Decimal("100"),
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal("25"),
        embedded_fee_amount_local=Decimal("20"),
        embedded_tax_amount_local=Decimal("5"),
        trade_fee=Decimal("100"),
        external_cash_transaction_id=None,
        epoch=7,
    )

    assert not should_generate_settlement_cash_leg(redemption)

    component = build_redemption_accrued_interest_component(redemption)

    assert component is not None
    assert component.transaction_id == "REDEMPTION-001-ACCRUED-INTEREST"
    assert component.component_id == "REDEMPTION-001-ACCRUED-INTEREST:v1"
    assert component.gross_transaction_amount == Decimal("25")
    assert component.external_cash_transaction_id is None
    assert component.linked_component_ids is None
    assert component.epoch == 7
    assert component.calculation_lineage == build_calculation_lineage(
        algorithm_id="redemption-accrued-interest-component",
        algorithm_version=1,
        intermediate_precision=64,
        input_payload={
            "source_transaction_id": "REDEMPTION-001",
            "source_transaction_type": "MATURITY_REDEMPTION",
            "source_calculation_lineage": None,
            "accrued_interest_proceeds_local": Decimal("25"),
            "canonical_net_settlement_amount": Decimal(0),
            "linked_cash_transaction_id": None,
        },
        output_payload={
            "transaction_id": "REDEMPTION-001-ACCRUED-INTEREST",
            "component_id": "REDEMPTION-001-ACCRUED-INTEREST:v1",
            "component_type": REDEMPTION_ACCRUED_INTEREST_COMPONENT,
            "amount": Decimal("25"),
            "currency": "USD",
        },
    )


@pytest.mark.parametrize("accrued_interest", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
def test_rejects_invalid_accrued_interest_evidence(accrued_interest: Decimal) -> None:
    with pytest.raises(ValueError, match="non-negative finite decimal"):
        build_redemption_accrued_interest_component(
            replace(
                _redemption(),
                accrued_interest_proceeds_local=accrued_interest,
                external_cash_transaction_id=None,
            )
        )


def test_rejects_negative_net_settlement_without_relaxing_cash_policy() -> None:
    redemption = replace(
        _redemption(),
        quantity=Decimal("1"),
        price=Decimal("100"),
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal("25"),
        embedded_fee_amount_local=Decimal("20"),
        embedded_tax_amount_local=Decimal("5"),
        trade_fee=Decimal("100.01"),
        external_cash_transaction_id=None,
    )

    with pytest.raises(SettlementCashValidationError):
        build_redemption_accrued_interest_component(redemption)


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


@pytest.mark.parametrize(
    "transaction_type",
    ["MATURITY_REDEMPTION", "CALL_REDEMPTION", "PARTIAL_REDEMPTION"],
)
@pytest.mark.parametrize(
    ("net_settlement_amount", "trade_fee"),
    [(Decimal("75"), Decimal("5")), (Decimal(0), Decimal("80"))],
)
@pytest.mark.parametrize(
    "calculation_context",
    [
        CashflowCalculationContext.CURRENT_BOOKING,
        CashflowCalculationContext.HISTORICAL_REBUILD,
    ],
)
def test_deductions_exceeding_principal_are_an_investment_outflow_component(
    transaction_type: str,
    net_settlement_amount: Decimal,
    trade_fee: Decimal,
    calculation_context: CashflowCalculationContext,
) -> None:
    interest_amount = Decimal("100")
    redemption = replace(
        _redemption(),
        transaction_type=transaction_type,
        quantity=Decimal(1),
        price=Decimal("10"),
        principal_proceeds_local=Decimal("10"),
        accrued_interest_proceeds_local=interest_amount,
        embedded_fee_amount_local=Decimal("20"),
        embedded_tax_amount_local=Decimal("10"),
        trade_fee=trade_fee,
        external_cash_transaction_id=(
            "REDEMPTION-001-CASHLEG" if net_settlement_amount > 0 else None
        ),
    )
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
        calculation_context=calculation_context,
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

    assert principal_cashflow.amount == net_settlement_amount - interest_amount
    assert principal_cashflow.classification == "INVESTMENT_OUTFLOW"
    assert income_cashflow.amount == interest_amount
    assert income_cashflow.classification == "INCOME"
    assert principal_cashflow.amount + income_cashflow.amount == net_settlement_amount


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
