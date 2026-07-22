"""Verify INTEREST settlement against reviewed, implementation-independent vectors."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CashflowClassification,
    CashflowRule,
    CashflowTiming,
    calculate_transaction_cashflow,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    calculate_interest_settlement_economics,
)
from tests.test_support.transaction_economics_reference import (
    evaluate_interest_settlement,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_VECTOR_PATH = (
    _REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "transaction_economics"
    / "interest_settlement.v1.json"
)
_REFERENCE_EVALUATOR_PATH = (
    _REPOSITORY_ROOT / "tests" / "test_support" / "transaction_economics_reference.py"
)
_FORBIDDEN_REFERENCE_IMPORT_ROOTS = frozenset({"portfolio_common", "src"})


def _load_vector_pack() -> dict[str, Any]:
    return json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))


_VECTOR_PACK = _load_vector_pack()


def _booked_interest(vector: dict[str, Any]) -> BookedTransaction:
    inputs = vector["inputs"]
    net_interest = inputs["net_interest_amount"]
    return BookedTransaction(
        transaction_id=vector["vector_id"],
        portfolio_id="PORTFOLIO-GOLDEN-001",
        instrument_id="BOND-GOLDEN-001",
        security_id="BOND-GOLDEN-001",
        transaction_date=datetime(2026, 4, 10, 10, 0),
        settlement_date=datetime(2026, 4, 12, 9, 0),
        transaction_type="INTEREST",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal(inputs["gross_interest_amount"]),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal(inputs["transaction_fee_amount"]),
        withholding_tax_amount=Decimal(inputs["withholding_tax_amount"]),
        other_interest_deductions_amount=Decimal(inputs["other_interest_deductions_amount"]),
        net_interest_amount=Decimal(net_interest) if net_interest is not None else None,
        interest_direction=inputs["direction"],
    )


def test_reference_evaluator_has_no_production_imports() -> None:
    tree = ast.parse(_REFERENCE_EVALUATOR_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.partition(".")[0])

    assert imported_roots.isdisjoint(_FORBIDDEN_REFERENCE_IMPORT_ROOTS)


def test_interest_vector_pack_declares_governance_metadata() -> None:
    assert _VECTOR_PACK["pack_id"] == "interest-settlement"
    assert _VECTOR_PACK["pack_version"] == "1.0.0"
    assert _VECTOR_PACK["methodology_policy"] == {
        "id": "interest-settlement-economics",
        "version": "1.0.0",
    }
    assert _VECTOR_PACK["rounding"] == {"mode": "none", "scale": None}

    for vector in _VECTOR_PACK["vectors"]:
        assert vector["vector_version"]
        assert vector["ordered_lifecycle_steps"]
        assert vector["tolerance"] == "0"
        assert vector["rationale"]
        assert vector["expected"]["quantity_delta"] == "0"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"net_interest_amount": "106"}, "does not reconcile"),
        ({"direction": "UNKNOWN"}, "Unsupported interest direction"),
    ],
)
def test_reference_evaluator_rejects_invalid_methodology_inputs(
    changes: dict[str, object],
    message: str,
) -> None:
    inputs = dict(_VECTOR_PACK["vectors"][0]["inputs"])
    inputs.update(changes)

    with pytest.raises(ValueError, match=message):
        evaluate_interest_settlement(inputs)


@pytest.mark.parametrize(
    "vector",
    _VECTOR_PACK["vectors"],
    ids=lambda vector: vector["vector_id"],
)
def test_interest_settlement_matches_independent_golden_vector(
    vector: dict[str, Any],
) -> None:
    expected = vector["expected"]
    reference = evaluate_interest_settlement(vector["inputs"])
    transaction = _booked_interest(vector)
    production = calculate_interest_settlement_economics(transaction)
    cashflow = calculate_transaction_cashflow(
        transaction,
        CashflowRule(
            classification=CashflowClassification.INCOME,
            timing=CashflowTiming.EOD,
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )

    assert reference.net_interest_amount == Decimal(expected["net_interest_amount"])
    assert reference.settlement_cash_amount == Decimal(expected["settlement_cash_amount"])
    assert reference.signed_cashflow_amount == Decimal(expected["signed_cashflow_amount"])
    assert production.net_interest_amount == reference.net_interest_amount
    assert production.settlement_cash_amount == reference.settlement_cash_amount
    assert cashflow.amount == reference.signed_cashflow_amount
    assert cashflow.cashflow_date.isoformat() == "2026-04-12"
    assert cashflow.timing == expected["cashflow_timing"]
