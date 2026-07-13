from pathlib import Path

from scripts.quality.domain_layer_guard import find_domain_import_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_domain_layer_guard_allows_pure_domain_imports(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/services/example_service/app/domain/policy.py",
        "from decimal import Decimal\n\nVALUE = Decimal('1')\n",
    )

    assert find_domain_import_findings(tmp_path) == []


def test_domain_layer_guard_rejects_framework_and_repository_imports(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/services/example_service/app/domain/policy.py",
        "from pydantic import BaseModel\nfrom app.repositories.positions import Repo\n",
    )

    findings = find_domain_import_findings(tmp_path)

    assert [finding.imported_module for finding in findings] == [
        "pydantic",
        "app.repositories.positions",
    ]


def test_domain_layer_guard_rejects_framework_models_in_fx_domain(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "src/services/portfolio_transaction_processing_service"
        / "app/domain/transaction/fx/models.py",
        "from pydantic import BaseModel\n",
    )
    _write(
        tmp_path / "src/services/example_service/app/domain/new_models.py",
        "from pydantic import BaseModel\n",
    )

    findings = find_domain_import_findings(tmp_path)

    assert [finding.path for finding in findings] == [
        "src/services/example_service/app/domain/new_models.py",
        "src/services/portfolio_transaction_processing_service/app/domain/transaction/fx/models.py",
    ]
