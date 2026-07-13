"""Verify ordinary settlement boundaries against independent golden vectors."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    SettlementCashValidationError,
    calculate_settlement_cash_movement,
)
from tests.test_support.transaction_economics_reference import (
    evaluate_ordinary_settlement_cash,
)

_VECTOR_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "transaction_economics"
    / "ordinary_settlement_cash.v1.json"
)
_VECTOR_PACK: dict[str, Any] = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))


def _booked_transaction(vector: dict[str, Any]) -> BookedTransaction:
    inputs = vector["inputs"]
    transaction_type = inputs["transaction_type"]
    is_interest = transaction_type == "INTEREST"
    return BookedTransaction(
        transaction_id=vector["vector_id"],
        portfolio_id="PORTFOLIO-GOLDEN-001",
        instrument_id="INSTRUMENT-GOLDEN-001",
        security_id="INSTRUMENT-GOLDEN-001",
        transaction_date=datetime(2026, 4, 10, 10, 0),
        settlement_date=datetime(2026, 4, 12, 9, 0),
        transaction_type=transaction_type,
        quantity=Decimal("1") if transaction_type == "SELL" else Decimal(0),
        price=Decimal("100") if transaction_type == "SELL" else Decimal(0),
        gross_transaction_amount=Decimal(
            inputs["gross_interest_amount"] if is_interest else inputs["gross_transaction_amount"]
        ),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal(inputs["transaction_fee_amount"]),
        withholding_tax_amount=(Decimal(inputs["withholding_tax_amount"]) if is_interest else None),
        other_interest_deductions_amount=(
            Decimal(inputs["other_interest_deductions_amount"]) if is_interest else None
        ),
        net_interest_amount=(Decimal(inputs["net_interest_amount"]) if is_interest else None),
        interest_direction=inputs.get("direction"),
    )


def test_ordinary_settlement_vector_pack_declares_governance_metadata() -> None:
    assert _VECTOR_PACK["pack_id"] == "ordinary-settlement-cash"
    assert _VECTOR_PACK["pack_version"] == "1.0.0"
    assert _VECTOR_PACK["methodology_policy"] == {
        "id": "ordinary-settlement-cash-boundary",
        "version": "1.0.0",
    }
    assert _VECTOR_PACK["rounding"] == {"mode": "none", "scale": None}

    assert len(_VECTOR_PACK["vectors"]) == 9
    for vector in _VECTOR_PACK["vectors"]:
        assert vector["vector_version"]
        assert vector["tolerance"] == "0"
        assert vector["rationale"]


@pytest.mark.parametrize(
    "vector",
    _VECTOR_PACK["vectors"],
    ids=lambda vector: vector["vector_id"],
)
def test_ordinary_settlement_matches_independent_golden_vector(
    vector: dict[str, Any],
) -> None:
    expected = vector["expected"]
    reference = evaluate_ordinary_settlement_cash(vector["inputs"])
    transaction = _booked_transaction(vector)

    assert reference.accepted is expected["accepted"]
    assert reference.available_proceeds_amount == Decimal(expected["available_proceeds_amount"])
    assert reference.fee_amount == Decimal(expected["fee_amount"])
    assert reference.rejection_reason_code == expected["rejection_reason_code"]

    if expected["accepted"]:
        movement = calculate_settlement_cash_movement(transaction)
        assert reference.signed_cash_amount == Decimal(expected["signed_cash_amount"])
        assert movement.signed_amount == reference.signed_cash_amount
        return

    assert reference.signed_cash_amount is None
    with pytest.raises(SettlementCashValidationError) as raised:
        calculate_settlement_cash_movement(transaction)
    assert raised.value.reason_code.value == reference.rejection_reason_code
