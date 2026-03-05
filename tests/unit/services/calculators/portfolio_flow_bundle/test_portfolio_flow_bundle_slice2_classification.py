from datetime import datetime
from decimal import Decimal

from portfolio_common.database_models import CashflowRule
from portfolio_common.events import TransactionEvent

from src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic import (
    CashflowLogic,
)
from src.services.calculators.cashflow_calculator_service.app.core.enums import (
    CashflowClassification,
    CashflowTiming,
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

    cashflow = CashflowLogic.calculate(event, rule)

    assert cashflow.amount == Decimal("-10")
    assert cashflow.is_portfolio_flow is True
