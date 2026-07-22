"""Verify DIVIDEND settlement across independent golden economics layers."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CashflowClassification,
    CashflowRule,
    CashflowTiming,
    calculate_transaction_cashflow,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisCalculator,
    CostBasisTransaction,
    CostCalculationErrorCollector,
)
from src.services.portfolio_transaction_processing_service.app.domain.position.reducer import (
    PositionBalanceState,
    calculate_next_position_state,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    calculate_settlement_cash_movement,
)
from tests.test_support.transaction_economics_reference import evaluate_dividend_settlement

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_VECTOR_PATH = (
    _REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "transaction_economics"
    / "dividend_settlement.v1.json"
)
_REFERENCE_EVALUATOR_PATH = (
    _REPOSITORY_ROOT / "tests" / "test_support" / "transaction_economics_reference.py"
)
_FORBIDDEN_REFERENCE_IMPORT_ROOTS = frozenset({"portfolio_common", "src"})
_VECTOR_PACK: dict[str, Any] = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))


def _booked_dividend(vector: dict[str, Any]) -> BookedTransaction:
    inputs = vector["inputs"]
    return BookedTransaction(
        transaction_id=vector["vector_id"],
        portfolio_id="PORTFOLIO-GOLDEN-001",
        instrument_id="EQUITY-GOLDEN-001",
        security_id="EQUITY-GOLDEN-001",
        transaction_date=datetime(2026, 4, 10, 10, 0),
        settlement_date=datetime(2026, 4, 12, 9, 0),
        transaction_type="DIVIDEND",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal(inputs["gross_dividend_amount"]),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal(inputs["transaction_fee_amount"]),
        withholding_tax_amount=Decimal(inputs["withholding_tax_amount"]),
    )


def _cost_basis_transaction(vector: dict[str, Any]) -> CostBasisTransaction:
    inputs = vector["inputs"]
    return CostBasisTransaction(
        transaction_id=vector["vector_id"],
        portfolio_id="PORTFOLIO-GOLDEN-001",
        instrument_id="EQUITY-GOLDEN-001",
        security_id="EQUITY-GOLDEN-001",
        transaction_type="DIVIDEND",
        transaction_date=datetime(2026, 4, 10, 10, 0),
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal(inputs["gross_dividend_amount"]),
        fees={"brokerage": Decimal(inputs["transaction_fee_amount"])},
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1"),
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


def test_dividend_vector_pack_declares_governance_metadata() -> None:
    assert _VECTOR_PACK["pack_id"] == "dividend-settlement"
    assert _VECTOR_PACK["pack_version"] == "1.1.0"
    assert _VECTOR_PACK["methodology_policy"] == {
        "id": "dividend-settlement-economics",
        "version": "1.1.0",
    }
    assert _VECTOR_PACK["rounding"] == {"mode": "none", "scale": None}
    for vector in _VECTOR_PACK["vectors"]:
        assert vector["vector_version"]
        assert vector["tolerance"] == "0"
        assert vector["rationale"]


@pytest.mark.parametrize(
    "vector",
    _VECTOR_PACK["vectors"],
    ids=lambda vector: vector["vector_id"],
)
def test_dividend_settlement_matches_independent_golden_vector(
    vector: dict[str, Any],
) -> None:
    expected = vector["expected"]
    reference = evaluate_dividend_settlement(vector["inputs"])
    transaction = _booked_dividend(vector)

    movement = calculate_settlement_cash_movement(transaction)
    cashflow = calculate_transaction_cashflow(
        transaction,
        CashflowRule(
            classification=CashflowClassification.INCOME,
            timing=CashflowTiming.EOD,
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )
    before = PositionBalanceState(
        quantity=Decimal("17"),
        cost_basis=Decimal("1250"),
        cost_basis_local=Decimal("1250"),
    )
    after = calculate_next_position_state(before, transaction)
    cost_transaction = _cost_basis_transaction(vector)
    error_reporter = CostCalculationErrorCollector()
    calculator = CostBasisCalculator(
        disposition_engine=MagicMock(),
        error_reporter=error_reporter,
    )
    calculator.calculate_transaction_costs(cost_transaction)

    assert not error_reporter.has_errors()
    assert reference.settlement_cash_amount == Decimal(expected["settlement_cash_amount"])
    assert reference.signed_cashflow_amount == Decimal(expected["signed_cashflow_amount"])
    assert reference.quantity_delta == Decimal(expected["quantity_delta"])
    assert reference.cost_basis_delta == Decimal(expected["cost_basis_delta"])
    assert reference.cost_basis_local_delta == Decimal(expected["cost_basis_local_delta"])
    assert reference.net_cost_amount == Decimal(expected["net_cost_amount"])
    assert reference.net_cost_local_amount == Decimal(expected["net_cost_local_amount"])
    assert reference.realized_total_pnl == Decimal(expected["realized_total_pnl"])
    assert reference.realized_total_pnl_local == Decimal(expected["realized_total_pnl_local"])
    assert movement.signed_amount == reference.settlement_cash_amount
    assert cashflow.amount == reference.signed_cashflow_amount
    assert cashflow.cashflow_date.isoformat() == "2026-04-12"
    assert cashflow.classification == "INCOME"
    assert cashflow.timing == expected["cashflow_timing"]
    assert after.quantity - before.quantity == reference.quantity_delta
    assert after.cost_basis - before.cost_basis == reference.cost_basis_delta
    assert after.cost_basis_local - before.cost_basis_local == reference.cost_basis_local_delta
    assert cost_transaction.net_cost == reference.net_cost_amount
    assert cost_transaction.net_cost_local == reference.net_cost_local_amount
    assert cost_transaction.net_cost == Decimal(expected["net_cost_amount"])
    assert cost_transaction.net_cost_local == Decimal(expected["net_cost_local_amount"])
    assert cost_transaction.gross_cost == Decimal(expected["net_cost_amount"])
    assert cost_transaction.realized_gain_loss == Decimal(expected["realized_total_pnl"])
    assert cost_transaction.realized_gain_loss == reference.realized_total_pnl
    assert cost_transaction.realized_gain_loss_local == reference.realized_total_pnl_local
    assert cost_transaction.realized_gain_loss_local == Decimal(
        expected["realized_total_pnl_local"]
    )


def test_reference_evaluator_rejects_non_positive_dividend_settlement() -> None:
    with pytest.raises(ValueError, match="settlement cash"):
        evaluate_dividend_settlement(
            {
                "gross_dividend_amount": "100",
                "withholding_tax_amount": "0",
                "transaction_fee_amount": "100",
            }
        )
