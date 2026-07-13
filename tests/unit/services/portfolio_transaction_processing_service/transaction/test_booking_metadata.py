"""Verify deterministic booking linkage and calculation-policy metadata."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BUY_DEFAULT_POLICY_ID,
    BUY_DEFAULT_POLICY_VERSION,
    DIVIDEND_DEFAULT_POLICY_ID,
    DIVIDEND_DEFAULT_POLICY_VERSION,
    INTEREST_DEFAULT_POLICY_ID,
    INTEREST_DEFAULT_POLICY_VERSION,
    SELL_AVCO_POLICY_ID,
    SELL_DEFAULT_POLICY_VERSION,
    SELL_FIFO_POLICY_ID,
    BookedTransaction,
    enrich_booking_metadata,
)


def _transaction(transaction_type: str) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"{transaction_type.strip()}-LINK-001",
        portfolio_id="PORT-LINK-001",
        instrument_id="SEC-ABC",
        security_id="SEC-ABC",
        transaction_date=datetime(2026, 3, 1, 12, 0, 0),
        transaction_type=transaction_type,
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )


@pytest.mark.parametrize(
    ("transaction_type", "policy_id", "policy_version", "cash_entry_mode"),
    [
        (" buy ", BUY_DEFAULT_POLICY_ID, BUY_DEFAULT_POLICY_VERSION, None),
        (" sell ", SELL_FIFO_POLICY_ID, SELL_DEFAULT_POLICY_VERSION, None),
        (
            " dividend ",
            DIVIDEND_DEFAULT_POLICY_ID,
            DIVIDEND_DEFAULT_POLICY_VERSION,
            "AUTO_GENERATE",
        ),
        (
            " interest ",
            INTEREST_DEFAULT_POLICY_ID,
            INTEREST_DEFAULT_POLICY_VERSION,
            "AUTO_GENERATE",
        ),
    ],
)
def test_booking_metadata_populates_family_defaults(
    transaction_type: str,
    policy_id: str,
    policy_version: str,
    cash_entry_mode: str | None,
) -> None:
    transaction = _transaction(transaction_type)

    enriched = enrich_booking_metadata(transaction)

    normalized_type = transaction_type.strip().upper()
    assert enriched.economic_event_id == (
        f"EVT-{normalized_type}-PORT-LINK-001-{transaction.transaction_id}"
    )
    assert enriched.linked_transaction_group_id == (
        f"LTG-{normalized_type}-PORT-LINK-001-{transaction.transaction_id}"
    )
    assert enriched.calculation_policy_id == policy_id
    assert enriched.calculation_policy_version == policy_version
    assert enriched.cash_entry_mode == cash_entry_mode


def test_booking_metadata_preserves_upstream_values() -> None:
    transaction = replace(
        _transaction("DIVIDEND"),
        economic_event_id="EVT-UPSTREAM-001",
        linked_transaction_group_id="LTG-UPSTREAM-001",
        calculation_policy_id="DIVIDEND_SPECIAL_POLICY",
        calculation_policy_version="2.1.0",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="CASH-UPSTREAM-001",
    )

    enriched = enrich_booking_metadata(transaction)

    assert enriched.economic_event_id == "EVT-UPSTREAM-001"
    assert enriched.linked_transaction_group_id == "LTG-UPSTREAM-001"
    assert enriched.calculation_policy_id == "DIVIDEND_SPECIAL_POLICY"
    assert enriched.calculation_policy_version == "2.1.0"
    assert enriched.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert enriched.external_cash_transaction_id == "CASH-UPSTREAM-001"


def test_sell_booking_metadata_uses_avco_policy_when_requested() -> None:
    enriched = enrich_booking_metadata(_transaction("SELL"), cost_basis_method="AVCO")

    assert enriched.calculation_policy_id == SELL_AVCO_POLICY_ID


def test_sell_booking_metadata_rejects_legacy_average_cost_alias() -> None:
    with pytest.raises(ValueError, match="Unsupported cost basis method"):
        enrich_booking_metadata(_transaction("SELL"), cost_basis_method="AVERAGE_COST")


def test_unrelated_transaction_is_returned_unchanged() -> None:
    transaction = _transaction("TRANSFER_IN")

    assert enrich_booking_metadata(transaction) is transaction
