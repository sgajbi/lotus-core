from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from portfolio_common.database_models import CashflowRule
from portfolio_common.events import TransactionEvent

from src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic import (
    CashflowLogic,
)
from src.services.calculators.cashflow_calculator_service.app.core.enums import (
    CashflowClassification,
    CashflowTiming,
)
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.core.position_models import (
    PositionState as PositionStateDTO,
)


def _event(
    transaction_type: str,
    *,
    quantity: str = "0",
    gross: str = "100",
    net_cost: str = "0",
    net_cost_local: str = "0",
    trade_fee: str = "0",
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=f"SLICE0_{transaction_type}_01",
        portfolio_id="PORT_074",
        instrument_id="INST_074",
        security_id="SEC_074",
        transaction_date=datetime(2026, 3, 5, 10, 0, 0),
        transaction_type=transaction_type,
        quantity=Decimal(quantity),
        price=Decimal("1"),
        gross_transaction_amount=Decimal(gross),
        trade_fee=Decimal(trade_fee),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal(net_cost),
        net_cost_local=Decimal(net_cost_local),
    )


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "gross", "net_cost", "expected_qty", "expected_cost"),
    [
        ("DEPOSIT", "0", "25", "0", Decimal("125"), Decimal("125")),
        ("WITHDRAWAL", "0", "30", "0", Decimal("70"), Decimal("70")),
        ("FEE", "0", "5", "0", Decimal("95"), Decimal("95")),
        ("TAX", "0", "7", "0", Decimal("93"), Decimal("93")),
        ("TRANSFER_IN", "2", "20", "0", Decimal("102"), Decimal("120")),
        ("TRANSFER_OUT", "3", "0", "-15", Decimal("97"), Decimal("85")),
    ],
)
def test_slice0_position_characterization_locks_current_bundle_behavior(
    transaction_type: str,
    quantity: str,
    gross: str,
    net_cost: str,
    expected_qty: Decimal,
    expected_cost: Decimal,
):
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
    )
    txn = _event(
        transaction_type,
        quantity=quantity,
        gross=gross,
        net_cost=net_cost,
        net_cost_local=net_cost,
    )

    next_state = PositionCalculator.calculate_next_position(initial_state, txn)

    assert next_state.quantity == expected_qty
    assert next_state.cost_basis == expected_cost
    assert next_state.cost_basis_local == expected_cost


@pytest.mark.parametrize(
    ("transaction_type", "classification", "timing", "is_portfolio_flow", "expected_amount"),
    [
        ("DEPOSIT", CashflowClassification.CASHFLOW_IN, CashflowTiming.BOD, True, Decimal("100")),
        (
            "WITHDRAWAL",
            CashflowClassification.CASHFLOW_OUT,
            CashflowTiming.EOD,
            True,
            Decimal("-100"),
        ),
        ("FEE", CashflowClassification.EXPENSE, CashflowTiming.EOD, True, Decimal("-100")),
        # Slice-0 lock: TAX currently carries is_portfolio_flow=False in seed rules.
        ("TAX", CashflowClassification.EXPENSE, CashflowTiming.EOD, False, Decimal("-100")),
        ("TRANSFER_IN", CashflowClassification.TRANSFER, CashflowTiming.BOD, True, Decimal("100")),
        (
            "TRANSFER_OUT",
            CashflowClassification.TRANSFER,
            CashflowTiming.EOD,
            True,
            Decimal("-100"),
        ),
    ],
)
@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_slice0_cashflow_characterization_locks_current_bundle_behavior(
    mock_metric,
    transaction_type: str,
    classification: str,
    timing: str,
    is_portfolio_flow: bool,
    expected_amount: Decimal,
):
    txn = _event(transaction_type, gross="100", trade_fee="0")
    rule = CashflowRule(
        classification=classification,
        timing=timing,
        is_position_flow=True,
        is_portfolio_flow=is_portfolio_flow,
    )

    cashflow = CashflowLogic.calculate(txn, rule)

    assert cashflow.amount == expected_amount
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is is_portfolio_flow
    mock_metric.labels.return_value.inc.assert_called_once()
