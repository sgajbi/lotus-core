from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import resolve_effective_processing_transaction_type


def _base_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="FX-PROC-001",
        portfolio_id="PORT-001",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0),
        transaction_type="FX_FORWARD",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1095000"),
        trade_currency="USD",
        currency="USD",
    )


def test_effective_processing_type_defaults_to_transaction_type() -> None:
    assert resolve_effective_processing_transaction_type(_base_event()) == "FX_FORWARD"


def test_effective_processing_type_prefers_fx_component_type() -> None:
    event = _base_event().model_copy(update={"component_type": "FX_CASH_SETTLEMENT_BUY"})
    assert resolve_effective_processing_transaction_type(event) == "FX_CASH_SETTLEMENT_BUY"
