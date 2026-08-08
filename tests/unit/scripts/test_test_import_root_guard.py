"""Prove canonical test import-root enforcement."""

from pathlib import Path

from scripts.quality.test_import_root_guard import find_legacy_test_imports


def test_guard_detects_from_and_direct_legacy_service_imports(tmp_path: Path) -> None:
    test_root = tmp_path / "tests"
    test_root.mkdir()
    (test_root / "test_legacy.py").write_text(
        "from services.query_service.app import main\n"
        "import services.portfolio_transaction_processing_service\n",
        encoding="utf-8",
    )

    findings = find_legacy_test_imports(root=tmp_path)

    assert [(finding.line_number, finding.module) for finding in findings] == [
        (1, "services.query_service.app"),
        (2, "services.portfolio_transaction_processing_service"),
    ]


def test_guard_accepts_canonical_and_relative_imports(tmp_path: Path) -> None:
    test_root = tmp_path / "tests"
    test_root.mkdir()
    (test_root / "test_canonical.py").write_text(
        "from src.services.query_service.app import main\nfrom .support import fixture\n",
        encoding="utf-8",
    )

    assert find_legacy_test_imports(root=tmp_path) == ()
