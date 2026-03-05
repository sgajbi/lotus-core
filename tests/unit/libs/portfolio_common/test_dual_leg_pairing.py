from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    DualLegPairingError,
    assert_upstream_cash_leg_pairing,
    validate_upstream_cash_leg_pairing,
)


def _base_product_leg() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-PROD-001",
        portfolio_id="PORT-001",
        instrument_id="SEC-ABC",
        security_id="SEC-ABC",
        transaction_date=datetime(2026, 3, 5, 12, 0, 0, tzinfo=UTC),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="TXN-CASH-001",
        economic_event_id="EVT-001",
        linked_transaction_group_id="LTG-001",
    )


def _base_cash_leg() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-CASH-001",
        portfolio_id="PORT-001",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime(2026, 3, 5, 12, 0, 0, tzinfo=UTC),
        transaction_type="ADJUSTMENT",
        quantity=Decimal("0"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        economic_event_id="EVT-001",
        linked_transaction_group_id="LTG-001",
    )


def test_validate_upstream_cash_leg_pairing_accepts_valid_pair() -> None:
    issues = validate_upstream_cash_leg_pairing(_base_product_leg(), _base_cash_leg())
    assert issues == []


def test_validate_upstream_cash_leg_pairing_rejects_mismatched_cash_leg() -> None:
    product_leg = _base_product_leg()
    cash_leg = _base_cash_leg().model_copy(
        update={
            "transaction_type": "BUY",
            "portfolio_id": "PORT-002",
            "gross_transaction_amount": Decimal("0"),
            "economic_event_id": "EVT-999",
        }
    )

    issues = validate_upstream_cash_leg_pairing(product_leg, cash_leg)
    fields = {issue.field for issue in issues}

    assert "portfolio_id" in fields
    assert "transaction_type" in fields
    assert "gross_transaction_amount" in fields
    assert "economic_event_id" in fields


def test_assert_upstream_cash_leg_pairing_raises_for_invalid_pair() -> None:
    product_leg = _base_product_leg().model_copy(update={"cash_entry_mode": "AUTO_GENERATE"})
    cash_leg = _base_cash_leg()

    with pytest.raises(DualLegPairingError):
        assert_upstream_cash_leg_pairing(product_leg, cash_leg)
