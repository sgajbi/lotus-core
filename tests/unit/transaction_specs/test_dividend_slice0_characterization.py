from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from core.enums.transaction_type import TransactionType
from core.models.transaction import Transaction as EngineTransaction
from logic.cost_calculator import CostCalculator
from logic.error_reporter import ErrorReporter
from portfolio_common.database_models import CashflowRule
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

from services.ingestion_service.app.DTOs.transaction_dto import Transaction
from src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic import (
    CashflowLogic,
)
from src.services.calculators.cashflow_calculator_service.app.core.enums import (
    CashflowClassification,
    CashflowTiming,
)
from src.services.calculators.cost_calculator_service.app.consumer import CostCalculatorConsumer
from src.services.calculators.position_calculator.app.core.position_logic import (
    PositionCalculator,
)
from src.services.calculators.position_calculator.app.core.position_models import (
    PositionState as PositionStateDTO,
)
from src.services.query_service.app.dtos.transaction_dto import TransactionRecord


def test_dividend_ingestion_allows_zero_quantity_and_price_with_default_fee() -> None:
    payload = {
        "transaction_id": "DIV_SLICE0_001",
        "portfolio_id": "PORT_SLICE0",
        "instrument_id": "SEC_EQ_US_001",
        "security_id": "SEC_EQ_US_001",
        "transaction_date": "2026-01-20T00:00:00Z",
        "transaction_type": "DIVIDEND",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "602.5",
        "trade_currency": "USD",
        "currency": "USD",
    }

    model = Transaction(**payload)
    assert model.transaction_type == "DIVIDEND"
    assert model.quantity == Decimal("0")
    assert model.price == Decimal("0")
    assert model.trade_fee == Decimal("0")


def test_dividend_fee_transformation_to_engine_fees_structure() -> None:
    consumer = CostCalculatorConsumer(
        bootstrap_servers="test",
        topic="raw_transactions_completed",
        group_id="slice0",
    )
    event = TransactionEvent(
        transaction_id="DIV_SLICE0_002",
        portfolio_id="PORT_SLICE0",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_date=datetime(2026, 1, 20),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("602.5"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("3.25"),
    )

    transformed = consumer._transform_event_for_engine(event)
    assert transformed["transaction_type"] == "DIVIDEND"
    assert transformed["fees"] == {"brokerage": "3.25"}


def test_dividend_cost_calculation_current_behavior_zero_cost_and_no_realized_pnl() -> None:
    mock_disposition_engine = MagicMock()
    error_reporter = ErrorReporter()
    calculator = CostCalculator(
        disposition_engine=mock_disposition_engine, error_reporter=error_reporter
    )
    dividend_transaction = EngineTransaction(
        transaction_id="DIV_SLICE0_003",
        portfolio_id="PORT_SLICE0",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_type=TransactionType.DIVIDEND,
        transaction_date=datetime(2026, 1, 20),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("602.5"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    calculator.calculate_transaction_costs(dividend_transaction)

    assert dividend_transaction.net_cost == Decimal("0")
    assert dividend_transaction.net_cost_local == Decimal("0")
    assert dividend_transaction.gross_cost == Decimal("0")
    assert dividend_transaction.realized_gain_loss is None
    assert dividend_transaction.realized_gain_loss_local is None
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_position_calculation_preserves_quantity_and_cost_basis() -> None:
    state = PositionStateDTO(
        quantity=Decimal("10"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )
    event = TransactionEvent(
        transaction_id="DIV_SLICE0_004",
        portfolio_id="PORT_SLICE0",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_date=datetime(2026, 1, 20),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("602.5"),
        trade_currency="USD",
        currency="USD",
    )

    next_state = PositionCalculator.calculate_next_position(state, event)
    assert next_state.quantity == Decimal("10")
    assert next_state.cost_basis == Decimal("1000")
    assert next_state.cost_basis_local == Decimal("1000")


@patch(
    "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL"
)
def test_dividend_cashflow_current_behavior_positive_income_inflow(mock_metric) -> None:
    event = TransactionEvent(
        transaction_id="DIV_SLICE0_005",
        portfolio_id="PORT_SLICE0",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_date=datetime(2026, 1, 20, 10, 0, 0),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("602.5"),
        trade_fee=Decimal("2.5"),
        trade_currency="USD",
        currency="USD",
    )
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = CashflowLogic.calculate(event, rule)

    assert cashflow.amount == Decimal("600.0")
    assert cashflow.amount > 0
    assert cashflow.classification == "INCOME"
    mock_metric.labels.assert_called_once_with(classification="INCOME", timing="EOD")
    mock_metric.labels.return_value.inc.assert_called_once()


def test_dividend_query_record_mapping_preserves_current_fields() -> None:
    db_txn = DBTransaction(
        transaction_id="DIV_SLICE0_006",
        transaction_date=datetime(2026, 1, 20),
        transaction_type="DIVIDEND",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("602.5"),
        currency="USD",
        net_cost=Decimal("0"),
        realized_gain_loss=None,
    )

    record = TransactionRecord.model_validate(db_txn)
    assert record.transaction_type == "DIVIDEND"
    assert record.quantity == 0.0
    assert record.net_cost == 0.0
    assert record.realized_gain_loss is None
