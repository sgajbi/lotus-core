from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from cost_engine.domain.enums.transaction_type import (
    TransactionType,
)
from cost_engine.domain.models.transaction import (
    Transaction as EngineTransaction,
)
from cost_engine.processing.cost_calculator import (
    CostCalculator,
)
from cost_engine.processing.error_reporter import (
    ErrorReporter,
)
from portfolio_common.database_models import Transaction as DBTransaction

from services.ingestion_service.app.DTOs.transaction_dto import Transaction
from src.services.query_service.app.dtos.transaction_dto import TransactionRecord


def test_fx_ingestion_accepts_canonical_foundation_fields() -> None:
    payload = {
        "transaction_id": "FX-SLICE0-001",
        "portfolio_id": "PORT-FX",
        "instrument_id": "FXC-EURUSD-001",
        "security_id": "FXC-EURUSD-001",
        "transaction_date": "2026-04-01T09:00:00Z",
        "transaction_type": "FX_FORWARD",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "1095000",
        "trade_currency": "USD",
        "currency": "USD",
        "settlement_date": "2026-07-01T09:00:00Z",
        "component_type": "FX_CONTRACT_OPEN",
        "component_id": "FX-COMP-OPEN-001",
        "linked_component_ids": ["FX-COMP-BUY-001", "FX-COMP-SELL-001"],
        "pair_base_currency": "EUR",
        "pair_quote_currency": "USD",
        "fx_rate_quote_convention": "QUOTE_PER_BASE",
        "buy_currency": "USD",
        "sell_currency": "EUR",
        "buy_amount": "1095000",
        "sell_amount": "1000000",
        "contract_rate": "1.095",
        "fx_contract_id": "FXC-2026-0001",
        "spot_exposure_model": "NONE",
        "fx_realized_pnl_mode": "UPSTREAM_PROVIDED",
        "realized_capital_pnl_local": "0",
        "realized_fx_pnl_local": "1250",
        "realized_total_pnl_local": "1250",
    }

    model = Transaction(**payload)

    assert model.transaction_type == "FX_FORWARD"
    assert model.component_type == "FX_CONTRACT_OPEN"
    assert model.fx_contract_id == "FXC-2026-0001"
    assert model.buy_amount == Decimal("1095000")


def test_fx_query_record_maps_foundation_fields() -> None:
    db_txn = DBTransaction(
        transaction_id="FX-SLICE0-002",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0),
        transaction_type="FX_SPOT",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("13450"),
        currency="SGD",
        component_type="FX_CASH_SETTLEMENT_BUY",
        component_id="FX-COMP-BUY-001",
        fx_cash_leg_role="BUY",
        linked_fx_cash_leg_id="FX-SLICE0-003",
        pair_base_currency="USD",
        pair_quote_currency="SGD",
        buy_currency="SGD",
        sell_currency="USD",
        buy_amount=Decimal("13450"),
        sell_amount=Decimal("10000"),
        contract_rate=Decimal("1.345"),
    )

    record = TransactionRecord.model_validate(db_txn)

    assert record.component_type == "FX_CASH_SETTLEMENT_BUY"
    assert record.fx_cash_leg_role == "BUY"
    assert record.buy_amount == Decimal("13450")


def test_fx_transaction_types_are_registered_and_engine_uses_baseline_processing() -> None:
    assert TransactionType.is_valid("FX_SPOT")
    assert TransactionType.is_valid("FX_FORWARD")
    assert TransactionType.is_valid("FX_SWAP")

    error_reporter = ErrorReporter()
    calculator = CostCalculator(
        disposition_engine=MagicMock(),
        error_reporter=error_reporter,
    )
    fx_transaction = EngineTransaction(
        transaction_id="FX-SLICE0-003",
        portfolio_id="PORT-FX",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_type=TransactionType.FX_FORWARD,
        transaction_date=datetime(2026, 4, 1, 9, 0, 0),
        settlement_date=datetime(2026, 7, 1, 9, 0, 0),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1"),
        component_type="FX_CONTRACT_CLOSE",
        component_id="FX-COMP-CLOSE-003",
        linked_component_ids=["FX-COMP-BUY-003", "FX-COMP-SELL-003"],
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        fx_rate_quote_convention="QUOTE_PER_BASE",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        fx_contract_id="FXC-2026-0003",
        fx_contract_open_transaction_id="FX-SLICE0-003-OPEN",
        fx_realized_pnl_mode="NONE",
    )

    calculator.calculate_transaction_costs(fx_transaction)

    assert not error_reporter.has_errors_for("FX-SLICE0-003")
    assert fx_transaction.net_cost == Decimal("0")
    assert fx_transaction.net_cost_local == Decimal("0")
    assert fx_transaction.realized_gain_loss == Decimal("0")
    assert fx_transaction.realized_gain_loss_local == Decimal("0")
    assert fx_transaction.realized_fx_pnl_local == Decimal("0")
