from pathlib import Path

from scripts.application_command_result_guard import (
    find_application_command_result_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_modules(root: Path) -> None:
    _write(
        root / "src/services/ingestion_service/app/application/upload_commands.py",
        "class UploadPreviewCommand: pass\n"
        "class UploadCommitCommand: pass\n"
        "class UploadPreviewResult: pass\n"
        "class UploadCommitResult: pass\n",
    )
    _write(
        root / "src/services/query_service/app/application/lookup_catalog.py",
        "class PortfolioLookupQuery: pass\n"
        "class InstrumentLookupQuery: pass\n"
        "class CurrencyLookupQuery: pass\n"
        "class LookupCatalogResult: pass\n",
    )
    _write(
        root / "src/services/query_service/app/application/core_snapshot.py",
        "class CoreSnapshotIdentityCommand: pass\n"
        "class CoreSnapshotOptionsCommand: pass\n"
        "class CoreSnapshotSimulationCommand: pass\n",
    )


def test_application_command_result_guard_allows_application_contracts(
    tmp_path: Path,
) -> None:
    _write_required_modules(tmp_path)
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "UploadPreviewCommand\nUploadCommitCommand\nUploadPreviewResult\nUploadCommitResult\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/lookup_catalog_service.py",
        "PortfolioLookupQuery\nInstrumentLookupQuery\nCurrencyLookupQuery\nLookupCatalogResult\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/core_snapshot_service.py",
        "CoreSnapshotIdentityCommand\ncanonical_payload()\n",
    )

    assert find_application_command_result_findings(tmp_path) == []


def test_application_command_result_guard_rejects_api_dto_contracts(
    tmp_path: Path,
) -> None:
    _write_required_modules(tmp_path)
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "from ..DTOs.upload_dto import UploadPreviewResponse, UploadCommitResponse\n"
        "UploadRowError\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/lookup_catalog_service.py",
        "from ..dtos.lookup_dto import LookupItem, LookupResponse\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/core_snapshot_service.py",
        'request.model_dump(mode="json")\n',
    )

    findings = find_application_command_result_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "UploadPreviewCommand",
        "UploadCommitCommand",
        "UploadPreviewResult",
        "UploadCommitResult",
        "..DTOs.upload_dto",
        "UploadPreviewResponse",
        "UploadCommitResponse",
        "UploadRowError",
        "PortfolioLookupQuery",
        "InstrumentLookupQuery",
        "CurrencyLookupQuery",
        "LookupCatalogResult",
        "..dtos.lookup_dto",
        "LookupResponse",
        "LookupItem",
        "CoreSnapshotIdentityCommand",
        "canonical_payload()",
        'request.model_dump(mode="json")',
    ]


def test_application_command_result_guard_rejects_missing_symbol(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/application/upload_commands.py",
        "class UploadPreviewCommand: pass\n"
        "class UploadCommitCommand: pass\n"
        "class UploadPreviewResult: pass\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/application/lookup_catalog.py",
        "class PortfolioLookupQuery: pass\n"
        "class InstrumentLookupQuery: pass\n"
        "class CurrencyLookupQuery: pass\n"
        "class LookupCatalogResult: pass\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/application/core_snapshot.py",
        "class CoreSnapshotIdentityCommand: pass\n"
        "class CoreSnapshotOptionsCommand: pass\n"
        "class CoreSnapshotSimulationCommand: pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "UploadPreviewCommand\nUploadCommitCommand\nUploadPreviewResult\nUploadCommitResult\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/lookup_catalog_service.py",
        "PortfolioLookupQuery\nInstrumentLookupQuery\nCurrencyLookupQuery\nLookupCatalogResult\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/core_snapshot_service.py",
        "CoreSnapshotIdentityCommand\ncanonical_payload()\n",
    )

    findings = find_application_command_result_findings(tmp_path)

    assert findings[0].path == ("src/services/ingestion_service/app/application/upload_commands.py")
    assert findings[0].snippet == "class UploadCommitResult"
