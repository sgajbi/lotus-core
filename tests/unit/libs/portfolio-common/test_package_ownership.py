"""Protect explicit ownership boundaries in the shared portfolio package."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PACKAGE_ROOT = REPO_ROOT / "src" / "libs" / "portfolio-common" / "portfolio_common"
SHARED_TIMESERIES_MARKET_DATA_READER = (
    PACKAGE_ROOT / "infrastructure" / "persistence" / "timeseries_market_data_reader.py"
)
PORTFOLIO_AGGREGATION_LOGIC = (
    REPO_ROOT
    / "src"
    / "services"
    / "portfolio_aggregation_service"
    / "app"
    / "core"
    / "portfolio_timeseries_logic.py"
)
PYTHON_SOURCE_ROOTS = (REPO_ROOT / "src", REPO_ROOT / "tests", REPO_ROOT / "scripts")
GENERATED_DIRECTORY_NAMES = {".venv", "__pycache__", "build", "dist"}
DOMAIN_FORBIDDEN_DEPENDENCIES = {
    "confluent_kafka",
    "fastapi",
    "httpx",
    "pydantic",
    "sqlalchemy",
    "starlette",
}
RETIRED_MODULES = {
    "portfolio_common.analytics_cashflow_semantics",
    "portfolio_common.cost_basis",
    "portfolio_common.currency_codes",
    "portfolio_common.decimal_amounts",
    "portfolio_common.domain_value_objects",
    "portfolio_common.domain.timeseries_market_data",
    "portfolio_common.fx_rates",
    "portfolio_common.market_prices",
    "portfolio_common.transaction_fee_components",
    "portfolio_common.transaction_type_registry",
    "portfolio_common.valuation_prices",
    "portfolio_common.ports.timeseries_market_data",
    "portfolio_common.control_code_normalization",
    "portfolio_common.models",
    "portfolio_common.infrastructure.persistence.timeseries_repository",
    "portfolio_common.timeseries_repository_base",
    "portfolio_common.transaction_domain.control_code_normalization",
    "portfolio_common.transaction_domain.effective_processing_type",
    "services.portfolio_aggregation_service.app.repositories.timeseries_repository",
    "src.services.portfolio_aggregation_service.app.repositories.timeseries_repository",
    "services.timeseries_generator_service.app.repositories.timeseries_repository",
    "src.services.timeseries_generator_service.app.repositories.timeseries_repository",
    "services.timeseries_generator_service.app.core.portfolio_timeseries_logic",
    "src.services.timeseries_generator_service.app.core.portfolio_timeseries_logic",
}
RETIRED_PATHS = {
    PACKAGE_ROOT / "analytics_cashflow_semantics.py",
    PACKAGE_ROOT / "cost_basis.py",
    PACKAGE_ROOT / "currency_codes.py",
    PACKAGE_ROOT / "decimal_amounts.py",
    PACKAGE_ROOT / "domain_value_objects.py",
    PACKAGE_ROOT / "domain" / "timeseries_market_data.py",
    PACKAGE_ROOT / "fx_rates.py",
    PACKAGE_ROOT / "market_prices.py",
    PACKAGE_ROOT / "transaction_fee_components.py",
    PACKAGE_ROOT / "transaction_type_registry.py",
    PACKAGE_ROOT / "valuation_prices.py",
    PACKAGE_ROOT / "ports" / "timeseries_market_data.py",
    PACKAGE_ROOT / "control_code_normalization.py",
    PACKAGE_ROOT / "models.py",
    PACKAGE_ROOT / "timeseries_repository_base.py",
    PACKAGE_ROOT / "infrastructure" / "persistence" / "timeseries_repository.py",
    PACKAGE_ROOT / "transaction_domain" / "control_code_normalization.py",
    PACKAGE_ROOT / "transaction_domain" / "effective_processing_type.py",
    REPO_ROOT
    / "src"
    / "services"
    / "portfolio_aggregation_service"
    / "app"
    / "repositories"
    / "timeseries_repository.py",
    REPO_ROOT
    / "src"
    / "services"
    / "timeseries_generator_service"
    / "app"
    / "repositories"
    / "timeseries_repository.py",
    REPO_ROOT
    / "tests"
    / "unit"
    / "services"
    / "portfolio_aggregation_service"
    / "repositories"
    / "test_timeseries_repository.py",
    REPO_ROOT
    / "tests"
    / "integration"
    / "services"
    / "timeseries_generator_service"
    / "test_int_timeseries_repo.py",
    REPO_ROOT
    / "tests"
    / "unit"
    / "services"
    / "timeseries_generator_service"
    / "timeseries-generator-service"
    / "repositories"
    / "test_unit_timeseries_repo.py",
    REPO_ROOT
    / "src"
    / "services"
    / "timeseries_generator_service"
    / "app"
    / "core"
    / "portfolio_timeseries_logic.py",
    REPO_ROOT
    / "tests"
    / "unit"
    / "services"
    / "timeseries_generator_service"
    / "timeseries-generator-service"
    / "core"
    / "test_portfolio_timeseries_logic.py",
}
AGGREGATION_QUEUE_METHODS = {
    "find_and_claim_eligible_jobs",
    "find_and_reset_stale_jobs",
    "get_job_queue_stats",
    "recover_dispatch_failed_jobs",
}


def _python_files() -> list[Path]:
    return sorted(
        path
        for source_root in PYTHON_SOURCE_ROOTS
        for path in source_root.rglob("*.py")
        if GENERATED_DIRECTORY_NAMES.isdisjoint(path.parts)
    )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    return imported_modules


def _retired_imports(path: Path) -> set[str]:
    return RETIRED_MODULES.intersection(_imported_modules(path))


def _import_roots(path: Path) -> set[str]:
    return {module.partition(".")[0] for module in _imported_modules(path)}


def test_retired_modules_are_absent() -> None:
    assert {path for path in RETIRED_PATHS if path.exists()} == set()


def test_source_does_not_import_retired_modules() -> None:
    violations = {
        path.relative_to(REPO_ROOT).as_posix(): sorted(imports)
        for path in _python_files()
        if (imports := _retired_imports(path))
    }
    assert violations == {}


def test_shared_domain_namespace_is_framework_independent() -> None:
    domain_root = PACKAGE_ROOT / "domain"
    violations = {
        path.relative_to(REPO_ROOT).as_posix(): sorted(forbidden_dependencies)
        for path in sorted(domain_root.rglob("*.py"))
        if (
            forbidden_dependencies := DOMAIN_FORBIDDEN_DEPENDENCIES.intersection(
                _import_roots(path)
            )
        )
    }
    assert violations == {}


def test_shared_timeseries_reader_exposes_only_common_market_data_methods() -> None:
    tree = ast.parse(
        SHARED_TIMESERIES_MARKET_DATA_READER.read_text(encoding="utf-8"),
        filename=str(SHARED_TIMESERIES_MARKET_DATA_READER),
    )
    class_methods = {
        child.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert class_methods == {"__init__", "get_fx_rate", "get_instruments_by_ids"}
    assert AGGREGATION_QUEUE_METHODS.isdisjoint(class_methods)


def test_portfolio_aggregation_logic_does_not_import_infrastructure() -> None:
    imported_modules = _imported_modules(PORTFOLIO_AGGREGATION_LOGIC)
    assert {module for module in imported_modules if "infrastructure" in module.split(".")} == set()
