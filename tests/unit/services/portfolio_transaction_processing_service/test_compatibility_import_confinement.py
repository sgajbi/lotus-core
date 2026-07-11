"""Guard the temporary calculator imports retained by transaction processing."""

from pathlib import Path


def test_transaction_service_has_no_legacy_calculator_imports() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    service_root = repo_root / "src/services/portfolio_transaction_processing_service"
    compatibility_import_files = [
        source.relative_to(service_root).as_posix()
        for source in (service_root / "app").rglob("*.py")
        if "src.services.calculators" in source.read_text(encoding="utf-8")
    ]

    assert compatibility_import_files == []
