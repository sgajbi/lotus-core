"""Protect domain-owned transaction infrastructure package boundaries."""

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]


def test_infrastructure_root_is_a_namespace_without_broad_exports() -> None:
    """Require callers to name the infrastructure capability they depend on."""

    package_root = (
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/__init__.py"
    )
    module = ast.parse(package_root.read_text(encoding="utf-8"))
    implementation_nodes = [
        node
        for node in module.body
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]

    assert implementation_nodes == []
