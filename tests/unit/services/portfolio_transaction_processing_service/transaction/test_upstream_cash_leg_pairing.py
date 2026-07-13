"""Verify upstream-provided product/cash settlement pairing invariants."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    UpstreamCashLegPairingError,
    assert_upstream_cash_leg_pairing,
    validate_upstream_cash_leg_pairing,
)


def _product_leg() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TXN-PROD-001",
        portfolio_id="PORT-001",
        instrument_id="SEC-ABC",
        security_id="SEC-ABC",
        transaction_date=datetime(2026, 3, 5, 12, 0, 0, tzinfo=UTC),
        transaction_type="DIVIDEND",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="TXN-CASH-001",
        economic_event_id="EVT-001",
        linked_transaction_group_id="LTG-001",
    )


def _cash_leg() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TXN-CASH-001",
        portfolio_id="PORT-001",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime(2026, 3, 5, 12, 0, 0, tzinfo=UTC),
        transaction_type="ADJUSTMENT",
        quantity=Decimal(0),
        price=Decimal(1),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        economic_event_id="EVT-001",
        linked_transaction_group_id="LTG-001",
    )


def test_upstream_pairing_accepts_valid_normalized_pair() -> None:
    cash_leg = replace(_cash_leg(), transaction_type=" adjustment ")

    assert validate_upstream_cash_leg_pairing(_product_leg(), cash_leg) == []


def test_upstream_pairing_reports_every_mismatch() -> None:
    cash_leg = replace(
        _cash_leg(),
        transaction_id="WRONG-CASH-ID",
        transaction_type="BUY",
        portfolio_id="PORT-002",
        gross_transaction_amount=Decimal(0),
        economic_event_id="EVT-999",
        linked_transaction_group_id="LTG-999",
    )

    fields = {issue.field for issue in validate_upstream_cash_leg_pairing(_product_leg(), cash_leg)}

    assert fields == {
        "economic_event_id",
        "external_cash_transaction_id",
        "gross_transaction_amount",
        "linked_transaction_group_id",
        "portfolio_id",
        "transaction_type",
    }


def test_upstream_pairing_requires_upstream_product_mode() -> None:
    product_leg = replace(_product_leg(), cash_entry_mode="AUTO_GENERATE")

    with pytest.raises(UpstreamCashLegPairingError):
        assert_upstream_cash_leg_pairing(product_leg, _cash_leg())
