from datetime import datetime
from decimal import Decimal

from portfolio_common.database_models import CashflowRule
from portfolio_common.events import TransactionEvent

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CashflowClassification,
    CashflowTiming,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CashflowCalculator,
)


def test_slice2_tax_rule_alignment_marks_portfolio_flow_true() -> None:
    event = TransactionEvent(
        transaction_id="TXN-TAX-074-01",
        portfolio_id="PORT-074",
        instrument_id="INST-074",
        security_id="SEC-074",
        transaction_date=datetime(2026, 3, 5, 12, 0, 0),
        transaction_type="TAX",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("10"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
    )
    rule = CashflowRule(
        transaction_type="TAX",
        classification=CashflowClassification.EXPENSE,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    cashflow = CashflowCalculator.calculate(event, rule)

    assert cashflow.amount == Decimal("-10")
    assert cashflow.is_portfolio_flow is True


def test_ca_transfer_classification_signs_for_in_and_out() -> None:
    rule = CashflowRule(
        transaction_type="MERGER_IN",
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )
    in_event = TransactionEvent(
        transaction_id="TXN-CA-IN-01",
        portfolio_id="PORT-074",
        instrument_id="INST-074",
        security_id="SEC-074",
        transaction_date=datetime(2026, 3, 5, 12, 0, 0),
        transaction_type="MERGER_IN",
        quantity=Decimal("10"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("100"),
        trade_fee=Decimal("0"),
        trade_currency="USD",
        currency="USD",
    )
    out_event = in_event.model_copy(
        update={"transaction_id": "TXN-CA-OUT-01", "transaction_type": "MERGER_OUT"}
    )

    in_cashflow = CashflowCalculator.calculate(in_event, rule)
    out_cashflow = CashflowCalculator.calculate(out_event, rule)

    assert in_cashflow.amount == Decimal("100")
    assert out_cashflow.amount == Decimal("-100")
