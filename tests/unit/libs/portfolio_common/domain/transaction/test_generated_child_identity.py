"""Verify deterministic generated transaction ownership classification."""

from types import SimpleNamespace

import pytest
from portfolio_common.domain.transaction import (
    TransactionIdentityFamily,
    require_generated_transaction_identity,
    transaction_identity_ownership,
)


def _candidate(**changes: object) -> SimpleNamespace:
    values = {
        "transaction_id": "SOURCE-001",
        "portfolio_id": "PORT-001",
        "transaction_type": "BUY",
        "originating_transaction_id": None,
        "originating_transaction_type": None,
        "cash_entry_mode": None,
        "component_type": None,
        "component_id": None,
        "link_type": None,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_classifies_canonical_generated_settlement_cash_identity() -> None:
    candidate = _candidate(
        transaction_id="DIVIDEND-001-CASHLEG",
        transaction_type="ADJUSTMENT",
        originating_transaction_id="DIVIDEND-001",
        originating_transaction_type="DIVIDEND",
        cash_entry_mode="AUTO_GENERATE",
        link_type="DIVIDEND_TO_CASH",
    )

    ownership = require_generated_transaction_identity(candidate)

    assert ownership.family is TransactionIdentityFamily.GENERATED_SETTLEMENT_CASH
    assert ownership.originating_transaction_id == "DIVIDEND-001"
    assert ownership.originating_transaction_type == "DIVIDEND"
    assert ownership.portfolio_id == "PORT-001"


def test_classifies_canonical_redemption_interest_identity() -> None:
    transaction_id = "MATURITY-001-ACCRUED-INTEREST"
    candidate = _candidate(
        transaction_id=transaction_id,
        transaction_type="INTEREST",
        originating_transaction_id="MATURITY-001",
        originating_transaction_type="MATURITY_REDEMPTION",
        component_type="REDEMPTION_ACCRUED_INTEREST",
        component_id=f"{transaction_id}:v1",
        link_type="REDEMPTION_TO_ACCRUED_INTEREST",
    )

    ownership = require_generated_transaction_identity(candidate)

    assert ownership.family is TransactionIdentityFamily.REDEMPTION_ACCRUED_INTEREST
    assert ownership.originating_transaction_id == "MATURITY-001"
    assert ownership.originating_transaction_type == "MATURITY_REDEMPTION"


@pytest.mark.parametrize(
    "changes",
    [
        {"originating_transaction_id": None},
        {"transaction_type": "BUY"},
        {"cash_entry_mode": None},
        {"originating_transaction_type": None},
        {"originating_transaction_type": "ADJUSTMENT", "link_type": "ADJUSTMENT_TO_CASH"},
        {"link_type": None},
        {"component_type": "UNRELATED"},
        {"component_id": "UPSTREAM-COMPONENT-1"},
    ],
)
def test_suffix_only_cash_masquerade_remains_source_owned(changes: dict[str, object]) -> None:
    candidate = _candidate(
        **(
            {
                "transaction_id": "SOURCE-001-CASHLEG",
                "transaction_type": "ADJUSTMENT",
                "originating_transaction_id": "SOURCE-001",
                "originating_transaction_type": "DIVIDEND",
                "cash_entry_mode": "AUTO_GENERATE",
                "link_type": "DIVIDEND_TO_CASH",
            }
            | changes
        )
    )

    assert transaction_identity_ownership(candidate).family is TransactionIdentityFamily.SOURCE
    with pytest.raises(ValueError, match="not a canonical generated child"):
        require_generated_transaction_identity(candidate)


@pytest.mark.parametrize(
    "changes",
    [
        {"originating_transaction_id": None},
        {"transaction_type": "ADJUSTMENT"},
        {"component_type": None},
        {"component_id": "wrong"},
        {"originating_transaction_type": "SELL"},
        {"link_type": None},
        {"link_type": "UNRELATED"},
    ],
)
def test_suffix_only_interest_masquerade_remains_source_owned(
    changes: dict[str, object],
) -> None:
    transaction_id = "MATURITY-001-ACCRUED-INTEREST"
    candidate = _candidate(
        **(
            {
                "transaction_id": transaction_id,
                "transaction_type": "INTEREST",
                "originating_transaction_id": "MATURITY-001",
                "originating_transaction_type": "MATURITY_REDEMPTION",
                "component_type": "REDEMPTION_ACCRUED_INTEREST",
                "component_id": f"{transaction_id}:v1",
                "link_type": "REDEMPTION_TO_ACCRUED_INTEREST",
            }
            | changes
        )
    )

    assert transaction_identity_ownership(candidate).family is TransactionIdentityFamily.SOURCE


@pytest.mark.parametrize("field_name", ["transaction_id", "portfolio_id"])
def test_rejects_blank_global_identity_fields(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        transaction_identity_ownership(_candidate(**{field_name: "  "}))
