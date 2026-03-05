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


@pytest.fixture
def base_transaction_event() -> TransactionEvent:
    """Provides a base, schema-valid transaction event that can be customized in tests."""
    return TransactionEvent(
        transaction_id="TXN_CASHFLOW_01",
        portfolio_id="PORT_CF_01",
        instrument_id="INST_CF_01",
        security_id="SEC_CF_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="BUY",  # Default type
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5.50"),
        trade_currency="USD",
        currency="USD",
    )


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_buy_transaction(mock_metric, base_transaction_event: TransactionEvent):
    """A BUY is a negative cashflow (outflow)."""
    # ARRANGE
    event = base_transaction_event
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    # ACT
    cashflow = CashflowLogic.calculate(event, rule)

    # ASSERT
    assert cashflow.amount < 0
    assert cashflow.amount == Decimal("-1005.50")
    assert cashflow.economic_event_id is None
    assert cashflow.linked_transaction_group_id is None
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False
    mock_metric.labels.assert_called_once_with(classification="INVESTMENT_OUTFLOW", timing="BOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_sell_transaction(mock_metric, base_transaction_event: TransactionEvent):
    """A SELL is a positive cashflow (inflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "SELL"
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_INFLOW,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    # ACT
    cashflow = CashflowLogic.calculate(event, rule)

    # ASSERT
    assert cashflow.amount > 0
    assert cashflow.amount == Decimal("994.50")
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False
    mock_metric.labels.assert_called_once_with(classification="INVESTMENT_INFLOW", timing="EOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_dividend_transaction(mock_metric, base_transaction_event: TransactionEvent):
    """A DIVIDEND is a positive cashflow (inflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "DIVIDEND"
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    # ACT
    cashflow = CashflowLogic.calculate(event, rule)

    # ASSERT
    assert cashflow.amount > 0
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False
    assert cashflow.timing == "EOD"
    mock_metric.labels.assert_called_once_with(classification="INCOME", timing="EOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_interest_income_transaction(
    mock_metric, base_transaction_event: TransactionEvent
):
    """INTEREST INCOME is a positive cashflow (inflow)."""
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "INTEREST",
            "gross_transaction_amount": Decimal("120"),
            "trade_fee": Decimal("5"),
            "interest_direction": "INCOME",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = CashflowLogic.calculate(event, rule)

    assert cashflow.amount == Decimal("115")
    assert cashflow.amount > 0
    mock_metric.labels.assert_called_once_with(classification="INCOME", timing="EOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_interest_expense_transaction(
    mock_metric, base_transaction_event: TransactionEvent
):
    """INTEREST EXPENSE is a negative cashflow (outflow)."""
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "INTEREST",
            "gross_transaction_amount": Decimal("120"),
            "trade_fee": Decimal("5"),
            "interest_direction": "EXPENSE",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = CashflowLogic.calculate(event, rule)

    assert cashflow.amount == Decimal("-115")
    assert cashflow.amount < 0
    mock_metric.labels.assert_called_once_with(classification="INCOME", timing="EOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_deposit_transaction(mock_metric, base_transaction_event: TransactionEvent):
    """A DEPOSIT is a positive cashflow (inflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "DEPOSIT"
    rule = CashflowRule(
        classification=CashflowClassification.CASHFLOW_IN,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = CashflowLogic.calculate(event, rule)

    # ASSERT
    assert cashflow.classification == "CASHFLOW_IN"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount > 0
    mock_metric.labels.assert_called_once_with(classification="CASHFLOW_IN", timing="BOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_fee_transaction(mock_metric, base_transaction_event: TransactionEvent):
    """A FEE is a negative cashflow (outflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "FEE"
    rule = CashflowRule(
        classification=CashflowClassification.EXPENSE,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = CashflowLogic.calculate(event, rule)

    # ASSERT
    assert cashflow.amount < 0
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True
    mock_metric.labels.assert_called_once_with(classification="EXPENSE", timing="EOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_withdrawal_transaction(mock_metric, base_transaction_event: TransactionEvent):
    """A WITHDRAWAL is a negative cashflow (outflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "WITHDRAWAL"
    event.gross_transaction_amount = Decimal("5000")
    event.trade_fee = Decimal("0")
    rule = CashflowRule(
        classification=CashflowClassification.CASHFLOW_OUT,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = CashflowLogic.calculate(event, rule)

    # ASSERT
    assert cashflow.amount == -event.gross_transaction_amount
    assert cashflow.classification == "CASHFLOW_OUT"
    assert cashflow.timing == "EOD"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True
    mock_metric.labels.assert_called_once_with(classification="CASHFLOW_OUT", timing="EOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_transfer_in_transaction(mock_metric, base_transaction_event: TransactionEvent):
    """A TRANSFER_IN is a positive cashflow (inflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "TRANSFER_IN"
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = CashflowLogic.calculate(event, rule)

    # ASSERT
    assert cashflow.classification == "TRANSFER"
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount > 0
    mock_metric.labels.assert_called_once_with(classification="TRANSFER", timing="BOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_transfer_out_transaction(mock_metric, base_transaction_event: TransactionEvent):
    """A TRANSFER_OUT is a negative cashflow (outflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "TRANSFER_OUT"
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = CashflowLogic.calculate(event, rule)

    # ASSERT
    assert cashflow.classification == "TRANSFER"
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount < 0
    mock_metric.labels.assert_called_once_with(classification="TRANSFER", timing="EOD")
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_buy_propagates_linkage_metadata(
    mock_metric, base_transaction_event: TransactionEvent
):
    """BUY cashflow should carry economic-event linkage metadata for reconciliation."""
    event = base_transaction_event
    event.economic_event_id = "EVT-2026-9001"
    event.linked_transaction_group_id = "LTG-2026-9001"
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = CashflowLogic.calculate(event, rule)

    assert cashflow.economic_event_id == "EVT-2026-9001"
    assert cashflow.linked_transaction_group_id == "LTG-2026-9001"
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_adjustment_inflow_uses_movement_direction(
    mock_metric, base_transaction_event: TransactionEvent
):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "ADJUSTMENT",
            "movement_direction": "INFLOW",
            "gross_transaction_amount": Decimal("250"),
            "trade_fee": Decimal("0"),
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.amount == Decimal("250")
    assert cashflow.amount > 0
    mock_metric.labels.return_value.inc.assert_called_once()


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_calculate_adjustment_outflow_uses_movement_direction(
    mock_metric, base_transaction_event: TransactionEvent
):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "ADJUSTMENT",
            "movement_direction": "OUTFLOW",
            "gross_transaction_amount": Decimal("250"),
            "trade_fee": Decimal("0"),
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.amount == Decimal("-250")
    assert cashflow.amount < 0
    mock_metric.labels.return_value.inc.assert_called_once()
