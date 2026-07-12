"""Guard the temporary calculator imports retained by transaction processing."""

from pathlib import Path


def test_transitional_calculator_imports_are_confined_to_infrastructure_adapters() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    service_root = repo_root / "src/services/portfolio_transaction_processing_service"
    compatibility_import_files = [
        source.relative_to(service_root).as_posix()
        for source in (service_root / "app").rglob("*.py")
        if "src.services.calculators" in source.read_text(encoding="utf-8")
    ]

    assert sorted(compatibility_import_files) == sorted(
        [
            "app/infrastructure/average_cost_pool_reconciliation_adapter.py",
            "app/infrastructure/cashflow_processing_adapter.py",
            "app/infrastructure/composition.py",
            "app/infrastructure/cost_processing_adapter.py",
            "app/infrastructure/position_processing_adapter.py",
            "app/infrastructure/sqlalchemy_unit_of_work.py",
        ]
    )
