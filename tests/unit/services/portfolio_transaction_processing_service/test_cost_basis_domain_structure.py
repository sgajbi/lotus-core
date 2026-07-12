"""Protect the target-owned cost-basis domain package structure."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
COST_BASIS_DOMAIN_ROOT = (
    REPO_ROOT
    / "src"
    / "services"
    / "portfolio_transaction_processing_service"
    / "app"
    / "domain"
    / "cost_basis"
)
RETIRED_COST_ENGINE_ROOT = (
    REPO_ROOT
    / "src"
    / "services"
    / "calculators"
    / "cost_calculator_service"
    / "app"
    / "cost_engine"
)
LEGACY_COST_APPLICATION_ROOT = (
    REPO_ROOT / "src" / "services" / "calculators" / "cost_calculator_service" / "app"
)


def test_cost_basis_domain_modules_have_responsibility_docstrings() -> None:
    missing_docstrings = []
    for module_path in COST_BASIS_DOMAIN_ROOT.rglob("*.py"):
        module = ast.parse(module_path.read_text(encoding="utf-8"))
        if ast.get_docstring(module) is None:
            missing_docstrings.append(module_path.relative_to(REPO_ROOT).as_posix())

    assert missing_docstrings == []


def test_legacy_cost_engine_package_is_retired() -> None:
    authored_files = [
        path
        for path in RETIRED_COST_ENGINE_ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    ]

    assert authored_files == []


def test_legacy_cost_checkpoint_modules_are_retired() -> None:
    assert not (LEGACY_COST_APPLICATION_ROOT / "average_cost_pool_checkpoint.py").exists()
    assert not (LEGACY_COST_APPLICATION_ROOT / "cost_processing_checkpoint.py").exists()


def test_legacy_cost_transaction_processor_is_retired() -> None:
    assert not (LEGACY_COST_APPLICATION_ROOT / "transaction_processor.py").exists()
    assert not (LEGACY_COST_APPLICATION_ROOT / "cost_calculation_processor.py").exists()


def test_cost_basis_calculation_modules_use_domain_specific_names() -> None:
    calculation_modules = {
        path.name for path in (COST_BASIS_DOMAIN_ROOT / "calculation").glob("*.py")
    }

    assert calculation_modules.isdisjoint(
        {
            "cost_calculator.py",
            "cost_objects.py",
            "disposition_engine.py",
            "error_reporter.py",
            "parser.py",
            "sorter.py",
        }
    )


def test_source_consumers_use_public_cost_basis_domain_api() -> None:
    private_prefix = "src.services.portfolio_transaction_processing_service.app.domain.cost_basis."
    offenders = []
    for module_path in (REPO_ROOT / "src").rglob("*.py"):
        if module_path.is_relative_to(COST_BASIS_DOMAIN_ROOT):
            continue
        if private_prefix in module_path.read_text(encoding="utf-8"):
            offenders.append(module_path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []
