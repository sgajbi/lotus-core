"""Protect transaction-processing runtime composition ownership."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]


def test_dependency_composition_uses_runtime_package() -> None:
    """Keep application assembly out of infrastructure implementation roots."""

    service_root = REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app"
    infrastructure_root = service_root / "infrastructure"
    root_exports = (infrastructure_root / "__init__.py").read_text(encoding="utf-8")

    assert (service_root / "runtime/dependency_composition.py").is_file()
    assert not (infrastructure_root / "composition.py").exists()
    assert not (
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_composition.py"
    ).exists()
    assert "build_process_transaction_use_case" not in root_exports
    assert "build_replay_booked_transaction_use_case" not in root_exports
    assert "build_reconcile_average_cost_pools_use_case" not in root_exports
