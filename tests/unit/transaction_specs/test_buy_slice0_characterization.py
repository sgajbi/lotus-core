from datetime import datetime
from decimal import Decimal

from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

from services.ingestion_service.app.DTOs.transaction_dto import Transaction
from src.services.calculators.cost_calculator_service.app.consumer import CostCalculatorConsumer
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.core.position_models import (
    PositionState as PositionStateDTO,
)
from src.services.query_service.app.dtos.transaction_dto import TransactionRecord


def test_buy_ingestion_transaction_defaults_trade_fee_to_zero() -> None:
    payload = {
        "transaction_id": "BUY_SLICE0_001",
        "portfolio_id": "PORT_SLICE0",
        "instrument_id": "SEC_UST_5Y",
        "security_id": "SEC_UST_5Y",
        "transaction_date": "2026-01-15T00:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10",
        "price": "99.25",
        "gross_transaction_amount": "992.5",
        "trade_currency": "USD",
        "currency": "USD",
    }

    model = Transaction(**payload)
    assert model.transaction_type == "BUY"
    assert model.trade_fee == Decimal("0")


def test_buy_fee_transformation_to_engine_fees_structure() -> None:
    consumer = CostCalculatorConsumer(
        bootstrap_servers="test",
        topic="transactions.persisted",
        group_id="slice0",
    )
    event = TransactionEvent(
        transaction_id="BUY_SLICE0_002",
        portfolio_id="PORT_SLICE0",
        instrument_id="SEC_UST_5Y",
        security_id="SEC_UST_5Y",
        transaction_date=datetime(2026, 1, 15),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("99.25"),
        gross_transaction_amount=Decimal("992.5"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("7.50"),
    )

    transformed = consumer._transform_event_for_engine(event)
    assert transformed["transaction_type"] == "BUY"
    assert transformed["fees"] == {"brokerage": "7.50"}


def test_buy_position_calculation_increases_quantity_and_cost_basis() -> None:
    state = PositionStateDTO(
        quantity=Decimal("0"),
        cost_basis=Decimal("0"),
        cost_basis_local=Decimal("0"),
    )
    event = TransactionEvent(
        transaction_id="BUY_SLICE0_003",
        portfolio_id="PORT_SLICE0",
        instrument_id="SEC_UST_5Y",
        security_id="SEC_UST_5Y",
        transaction_date=datetime(2026, 1, 15),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("99.25"),
        gross_transaction_amount=Decimal("992.5"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
    )

    next_state = PositionCalculator.calculate_next_position(state, event)
    assert next_state.quantity == Decimal("10")
    assert next_state.cost_basis == Decimal("1000")
    assert next_state.cost_basis_local == Decimal("1000")


def test_buy_query_record_mapping_preserves_current_fields() -> None:
    db_txn = DBTransaction(
        transaction_id="BUY_SLICE0_004",
        transaction_date=datetime(2026, 1, 15),
        transaction_type="BUY",
        instrument_id="SEC_UST_5Y",
        security_id="SEC_UST_5Y",
        quantity=Decimal("10"),
        price=Decimal("99.25"),
        gross_transaction_amount=Decimal("992.5"),
        currency="USD",
        net_cost=Decimal("1000"),
        realized_gain_loss=Decimal("0"),
    )

    record = TransactionRecord.model_validate(db_txn)
    assert record.transaction_type == "BUY"
    assert record.quantity == 10.0
    assert record.net_cost == 1000.0
    assert record.realized_gain_loss == 0.0
