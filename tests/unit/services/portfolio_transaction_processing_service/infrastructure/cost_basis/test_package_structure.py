"""Protect cost-basis infrastructure package ownership."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_corporate_action_observability_uses_cost_basis_package() -> None:
    """Keep corporate-action basis telemetry with cost-basis adapters."""

    source_root = (
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/infrastructure"
    )
    root_exports = (source_root / "__init__.py").read_text(encoding="utf-8")

    assert (source_root / "cost_basis/corporate_action_observability.py").is_file()
    assert not (source_root / "corporate_action_reconciliation_observability.py").exists()
    assert not (
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_corporate_action_reconciliation_observability.py"
    ).exists()
    assert "PrometheusCorporateActionReconciliationObserver" not in root_exports
