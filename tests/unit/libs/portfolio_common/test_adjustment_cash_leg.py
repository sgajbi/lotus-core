from datetime import datetime
from decimal import Decimal

import pytest
from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    AdjustmentCashLegError,
    build_auto_generated_adjustment_cash_leg,
    should_auto_generate_cash_leg,
)


def _base_dividend_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="DIV-001",
        portfolio_id="PORT-001",
        instrument_id="SEC-AAA",
        security_id="SEC-AAA",
        transaction_date=datetime(2026, 3, 5, 10, 0, 0),
        settlement_date=datetime(2026, 3, 6, 10, 0, 0),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("100.00"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("2.00"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-ACC-USD-001",
        settlement_cash_instrument_id="CASH-USD",
    )


def test_should_auto_generate_cash_leg_requires_explicit_settlement_account() -> None:
    event = _base_dividend_event().model_copy(update={"settlement_cash_account_id": None})
    assert should_auto_generate_cash_leg(event) is False


def test_build_auto_generated_adjustment_cash_leg_builds_linked_adjustment_event() -> None:
    cash_leg = build_auto_generated_adjustment_cash_leg(_base_dividend_event())
    assert cash_leg.transaction_type == "ADJUSTMENT"
    assert cash_leg.transaction_id == "DIV-001-CASHLEG"
    assert cash_leg.originating_transaction_id == "DIV-001"
    assert cash_leg.originating_transaction_type == "DIVIDEND"
    assert cash_leg.movement_direction == "INFLOW"
    assert cash_leg.gross_transaction_amount == Decimal("98.00")
    assert cash_leg.instrument_id == "CASH-USD"


def test_build_auto_generated_adjustment_cash_leg_rejects_non_eligible_transaction() -> None:
    event = _base_dividend_event().model_copy(
        update={"transaction_type": "DEPOSIT", "settlement_cash_account_id": "CASH-USD"}
    )
    with pytest.raises(AdjustmentCashLegError):
        build_auto_generated_adjustment_cash_leg(event)
