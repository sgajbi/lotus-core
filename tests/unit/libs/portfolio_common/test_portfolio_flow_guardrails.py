from datetime import datetime
from decimal import Decimal

import pytest
from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    assert_portfolio_flow_cash_entry_mode_allowed,
    is_portfolio_flow_no_auto_generate_transaction_type,
)


def _event(transaction_type: str, cash_entry_mode: str | None) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=f"TXN-{transaction_type}",
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


@pytest.mark.parametrize(
    ("transaction_type", "expected"),
    [
        ("FEE", True),
        ("TAX", True),
        ("DEPOSIT", True),
        ("WITHDRAWAL", True),
        ("TRANSFER_IN", True),
        ("TRANSFER_OUT", True),
        ("BUY", False),
        ("DIVIDEND", False),
    ],
)
def test_is_portfolio_flow_no_auto_generate_transaction_type(
    transaction_type: str, expected: bool
) -> None:
    assert is_portfolio_flow_no_auto_generate_transaction_type(transaction_type) is expected


@pytest.mark.parametrize(
    "transaction_type",
    ["FEE", "TAX", "DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT"],
)
def test_guardrail_rejects_auto_generate_for_portfolio_flows(transaction_type: str) -> None:
    with pytest.raises(ValueError, match="AUTO_GENERATE cash_entry_mode is not supported"):
        assert_portfolio_flow_cash_entry_mode_allowed(_event(transaction_type, "AUTO_GENERATE"))


def test_guardrail_allows_upstream_provided_for_portfolio_flows() -> None:
    assert_portfolio_flow_cash_entry_mode_allowed(_event("FEE", "UPSTREAM_PROVIDED"))


def test_guardrail_allows_auto_generate_for_non_portfolio_flow_types() -> None:
    assert_portfolio_flow_cash_entry_mode_allowed(_event("DIVIDEND", "AUTO_GENERATE"))
