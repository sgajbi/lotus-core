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


def test_transaction_domain_modules_have_responsibility_docstrings() -> None:
    missing_docstrings = []
    for module_path in TRANSACTION_DOMAIN_ROOT.rglob("*.py"):
        module = ast.parse(module_path.read_text(encoding="utf-8"))
        if ast.get_docstring(module) is None:
            missing_docstrings.append(module_path.relative_to(REPO_ROOT).as_posix())

    assert missing_docstrings == []


def test_flat_transaction_domain_modules_are_retired() -> None:
    assert [path for path in LEGACY_TRANSACTION_DOMAIN_MODULES if path.exists()] == []
