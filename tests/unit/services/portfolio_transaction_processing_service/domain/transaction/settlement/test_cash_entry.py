"""Verify canonical cash-entry mode and portfolio-flow policy."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    CashEntryMode,
    assert_cash_entry_mode_supported,
    is_portfolio_level_cash_flow,
    is_upstream_provided_cash_entry_mode,
    resolve_cash_entry_mode,
)


def _transaction(
    transaction_type: str = "DIVIDEND",
    cash_entry_mode: str | None = None,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"TXN-{transaction_type.strip()}",
        portfolio_id="PORT-1",
        instrument_id="INST-1",
        security_id="SEC-1",
        transaction_date=datetime(2026, 3, 5, 10, 0, 0),
        transaction_type=transaction_type,
        quantity=Decimal("1"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("10"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode=cash_entry_mode,
    )


def test_resolve_cash_entry_mode_defaults_to_auto_generate() -> None:
    assert resolve_cash_entry_mode(None) is CashEntryMode.AUTO_GENERATE


def test_resolve_cash_entry_mode_normalizes_known_values() -> None:
    assert resolve_cash_entry_mode(" upstream_provided ") is CashEntryMode.UPSTREAM_PROVIDED
    assert is_upstream_provided_cash_entry_mode("UPSTREAM_PROVIDED")
    assert not is_upstream_provided_cash_entry_mode("AUTO_GENERATE")


def test_resolve_cash_entry_mode_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unsupported cash_entry_mode"):
        resolve_cash_entry_mode("MANUAL")


@pytest.mark.parametrize(
    ("transaction_type", "expected"),
    [
        ("FEE", True),
        ("TAX", True),
        ("DEPOSIT", True),
        ("WITHDRAWAL", True),
        ("TRANSFER_IN", True),
        ("TRANSFER_OUT", True),
        (" fee ", True),
        ("BUY", False),
        (" deposit_reversal ", False),
        ("DIVIDEND", False),
    ],
)
def test_portfolio_level_cash_flow_classification(
    transaction_type: str,
    expected: bool,
) -> None:
    assert is_portfolio_level_cash_flow(transaction_type) is expected


@pytest.mark.parametrize(
    "transaction_type",
    ["FEE", "TAX", "DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT"],
)
def test_portfolio_level_cash_flows_reject_generated_cash_legs(
    transaction_type: str,
) -> None:
    transaction = _transaction(transaction_type, "AUTO_GENERATE")

    with pytest.raises(ValueError, match="AUTO_GENERATE cash_entry_mode is not supported"):
        assert_cash_entry_mode_supported(transaction)


def test_cash_entry_policy_normalizes_control_codes_before_validation() -> None:
    transaction = _transaction(" transfer_out ", " auto_generate ")

    with pytest.raises(ValueError, match="AUTO_GENERATE cash_entry_mode is not supported"):
        assert_cash_entry_mode_supported(transaction)


def test_cash_entry_policy_allows_upstream_or_non_portfolio_flows() -> None:
    assert_cash_entry_mode_supported(_transaction("FEE", "UPSTREAM_PROVIDED"))
    assert_cash_entry_mode_supported(_transaction("DIVIDEND", "AUTO_GENERATE"))
    assert_cash_entry_mode_supported(replace(_transaction("FEE"), cash_entry_mode=None))
