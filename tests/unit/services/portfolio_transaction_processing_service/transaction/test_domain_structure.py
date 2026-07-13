"""Protect transaction-processing domain ownership and package structure."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
TRANSACTION_DOMAIN_ROOT = (
    REPO_ROOT
    / "src"
    / "services"
    / "portfolio_transaction_processing_service"
    / "app"
    / "domain"
    / "transaction"
)
LEGACY_TRANSACTION_DOMAIN_MODULES = (
    TRANSACTION_DOMAIN_ROOT.parent / "booked_transaction.py",
    TRANSACTION_DOMAIN_ROOT.parent / "transaction_semantic_identity.py",
)
SHARED_TRANSACTION_DOMAIN_ROOT = (
    REPO_ROOT / "src" / "libs" / "portfolio-common" / "portfolio_common" / "transaction_domain"
)
RETIRED_SHARED_ORDINARY_TRANSACTION_MODULES = tuple(
    SHARED_TRANSACTION_DOMAIN_ROOT / module_name
    for module_name in (
        "adjustment_cash_leg.py",
        "buy_linkage.py",
        "buy_models.py",
        "buy_reason_codes.py",
        "buy_validation.py",
        "cash_entry_mode.py",
        "dividend_linkage.py",
        "dividend_models.py",
        "dividend_reason_codes.py",
        "dividend_validation.py",
        "dual_leg_pairing.py",
        "interest_linkage.py",
        "interest_models.py",
        "interest_reason_codes.py",
        "interest_validation.py",
        "portfolio_flow_guardrails.py",
        "sell_linkage.py",
        "sell_models.py",
        "sell_reason_codes.py",
        "sell_validation.py",
    )
)
RETIRED_SHARED_CORPORATE_ACTION_MODULES = tuple(
    SHARED_TRANSACTION_DOMAIN_ROOT / module_name
    for module_name in (
        "ca_bundle_a_reason_codes.py",
        "ca_bundle_a_reconciliation.py",
        "ca_bundle_a_validation.py",
    )
)


def test_transaction_domain_modules_have_responsibility_docstrings() -> None:
    missing_docstrings = []
    for module_path in TRANSACTION_DOMAIN_ROOT.rglob("*.py"):
        module = ast.parse(module_path.read_text(encoding="utf-8"))
        if ast.get_docstring(module) is None:
            missing_docstrings.append(module_path.relative_to(REPO_ROOT).as_posix())

    assert missing_docstrings == []


def test_flat_transaction_domain_modules_are_retired() -> None:
    assert [path for path in LEGACY_TRANSACTION_DOMAIN_MODULES if path.exists()] == []


def test_shared_ordinary_transaction_modules_are_retired() -> None:
    assert [
        path.relative_to(REPO_ROOT).as_posix()
        for path in RETIRED_SHARED_ORDINARY_TRANSACTION_MODULES
        if path.exists()
    ] == []


def test_shared_corporate_action_modules_are_retired() -> None:
    assert [
        path.relative_to(REPO_ROOT).as_posix()
        for path in RETIRED_SHARED_CORPORATE_ACTION_MODULES
        if path.exists()
    ] == []
