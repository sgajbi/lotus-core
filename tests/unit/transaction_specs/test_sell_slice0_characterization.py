from datetime import datetime
from decimal import Decimal

from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

from services.ingestion_service.app.DTOs.transaction_dto import Transaction
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    build_cost_basis_engine_input,
)
from src.services.portfolio_transaction_processing_service.app.domain.position.reducer import (
    PositionBalanceState as PositionStateDTO,
)
from src.services.portfolio_transaction_processing_service.app.domain.position.reducer import (
    calculate_next_position_state,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.booked_transaction_event_mapper import (  # noqa: E501
    to_booked_transaction,
)
from src.services.query_service.app.dtos.transaction_dto import TransactionRecord


def test_sell_ingestion_transaction_defaults_trade_fee_to_zero() -> None:
    payload = {
        "transaction_id": "SELL_SLICE0_001",
        "portfolio_id": "PORT_SLICE0",
        "instrument_id": "SEC_EQ_US_001",
        "security_id": "SEC_EQ_US_001",
        "transaction_date": "2026-01-20T00:00:00Z",
        "transaction_type": "SELL",
        "quantity": "5",
        "price": "120.50",
        "gross_transaction_amount": "602.5",
        "trade_currency": "USD",
        "currency": "USD",
    }

    model = Transaction(**payload)
    assert model.transaction_type == "SELL"
    assert model.trade_fee == Decimal("0")


def test_sell_fee_transformation_to_engine_fees_structure() -> None:
    event = TransactionEvent(
        transaction_id="SELL_SLICE0_002",
        portfolio_id="PORT_SLICE0",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_date=datetime(2026, 1, 20),
        transaction_type="SELL",
        quantity=Decimal("5"),
        price=Decimal("120.50"),
        gross_transaction_amount=Decimal("602.5"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("3.25"),
    )

    transformed = build_cost_basis_engine_input(to_booked_transaction(event))
    assert transformed["transaction_type"] == "SELL"
    assert transformed["fees"] == {"brokerage": "3.25"}


def test_sell_position_calculation_reduces_quantity_and_cost_basis() -> None:
    state = PositionStateDTO(
        quantity=Decimal("10"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )
    event = TransactionEvent(
        transaction_id="SELL_SLICE0_003",
        portfolio_id="PORT_SLICE0",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_date=datetime(2026, 1, 20),
        transaction_type="SELL",
        quantity=Decimal("5"),
        price=Decimal("120.50"),
        gross_transaction_amount=Decimal("602.5"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("-500"),
        net_cost_local=Decimal("-500"),
    )

    next_state = calculate_next_position_state(state, to_booked_transaction(event))
    assert next_state.quantity == Decimal("5")
    assert next_state.cost_basis == Decimal("500")
    assert next_state.cost_basis_local == Decimal("500")


def test_sell_query_record_mapping_preserves_current_fields() -> None:
    db_txn = DBTransaction(
        transaction_id="SELL_SLICE0_004",
        transaction_date=datetime(2026, 1, 20),
        transaction_type="SELL",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        quantity=Decimal("5"),
        price=Decimal("120.50"),
        gross_transaction_amount=Decimal("602.5"),
        currency="USD",
        net_cost=Decimal("-500"),
        realized_gain_loss=Decimal("102.5"),
    )

    record = TransactionRecord.model_validate(db_txn)
    assert record.transaction_type == "SELL"
    assert record.quantity == 5.0
    assert record.net_cost == -500.0
    assert record.realized_gain_loss == 102.5
