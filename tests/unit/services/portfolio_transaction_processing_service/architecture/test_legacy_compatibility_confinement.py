"""Guard the temporary calculator imports retained by transaction processing."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
SERVICE_ROOT = REPO_ROOT / "src/services/portfolio_transaction_processing_service"
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"


def test_legacy_compatibility_guard_is_architecture_owned() -> None:
    assert Path(__file__).resolve().parent == SERVICE_TEST_ROOT / "architecture"
    assert not (SERVICE_TEST_ROOT / "test_compatibility_import_confinement.py").exists()


def test_transaction_service_has_no_legacy_calculator_imports() -> None:
    compatibility_import_files = [
        source.relative_to(SERVICE_ROOT).as_posix()
        for source in (SERVICE_ROOT / "app").rglob("*.py")
        if "src.services.calculators" in source.read_text(encoding="utf-8")
    ]

    assert compatibility_import_files == []


def test_retired_legacy_event_mapper_is_absent() -> None:
    """Keep the obsolete mapper name from becoming a compatibility facade."""

    assert not (SERVICE_ROOT / "app/infrastructure/legacy_transaction_event_mapper.py").exists()
    assert not any(
        "legacy_transaction_event_mapper" in source.read_text(encoding="utf-8")
        for source in (SERVICE_ROOT / "app").rglob("*.py")
    )
