"""Protect transaction-processing coordination domain structure."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
SERVICE_TEST_ROOT = (
    REPO_ROOT / "tests" / "unit" / "services" / "portfolio_transaction_processing_service"
)
PROCESSING_DOMAIN_ROOT = (
    REPO_ROOT
    / "src"
    / "services"
    / "portfolio_transaction_processing_service"
    / "app"
    / "domain"
    / "processing"
)


def test_processing_structure_guard_is_domain_owned() -> None:
    assert Path(__file__).resolve().parent == SERVICE_TEST_ROOT / "domain" / "processing"
    assert not (SERVICE_TEST_ROOT / "test_processing_domain_structure.py").exists()


def test_processing_domain_modules_have_responsibility_docstrings() -> None:
    missing_docstrings = []
    for module_path in PROCESSING_DOMAIN_ROOT.rglob("*.py"):
        module = ast.parse(module_path.read_text(encoding="utf-8"))
        if ast.get_docstring(module) is None:
            missing_docstrings.append(module_path.relative_to(REPO_ROOT).as_posix())

    assert missing_docstrings == []


def test_flat_transaction_stage_module_is_retired() -> None:
    assert not (PROCESSING_DOMAIN_ROOT.parent / "transaction_stage.py").exists()
