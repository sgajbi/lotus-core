from pathlib import Path

from scripts.quality.upload_component_boundary_guard import (
    find_upload_component_boundary_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_upload_boundary(root: Path) -> None:
    _write(
        root / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "BulkUploadValidator\nUploadRecordPublisher\n"
        "ValidateTransactionPortfolioOwnership\nPortfolioTenantOwnershipReadError\n"
        'if command.entity_type != "transactions":\n'
        "await self._validate_transaction_portfolio_ownership(command, validation)\n"
        "publish_records(\n",
    )
    _write(
        root / "src/services/ingestion_service/app/services/upload_validation.py",
        "class BulkUploadValidator: pass\nclass UploadValidationReport: pass\n",
    )
    _write(
        root / "src/services/ingestion_service/app/services/upload_publishers.py",
        "class IngestionServiceUploadPublisher(UploadRecordPublisher): pass\n",
    )
    _write(
        root / "src/services/ingestion_service/app/ports/upload_record_publisher.py",
        "class UploadRecordPublisher:\n    async def publish_records(self): pass\n",
    )


def test_upload_component_boundary_guard_allows_split_components(tmp_path: Path) -> None:
    _write_required_upload_boundary(tmp_path)

    assert find_upload_component_boundary_findings(tmp_path) == []


def test_upload_component_boundary_guard_requires_transaction_tenant_authority(
    tmp_path: Path,
) -> None:
    _write_required_upload_boundary(tmp_path)
    service_path = (
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py"
    )
    service_path.write_text(
        service_path.read_text(encoding="utf-8").replace(
            "await self._validate_transaction_portfolio_ownership(command, validation)\n",
            "",
        ),
        encoding="utf-8",
    )

    findings = find_upload_component_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "await self._validate_transaction_portfolio_ownership(command, validation)"
    ]


def test_upload_component_boundary_guard_rejects_monolithic_upload_service(
    tmp_path: Path,
) -> None:
    _write_required_upload_boundary(tmp_path)
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "BulkUploadValidator\nUploadRecordPublisher\n"
        "ValidateTransactionPortfolioOwnership\nPortfolioTenantOwnershipReadError\n"
        'if command.entity_type != "transactions":\n'
        "await self._validate_transaction_portfolio_ownership(command, validation)\n"
        "publish_records(\n"
        "from .ingestion_service import IngestionService\n"
        "csv.DictReader\nload_workbook\ndef _publish_transactions(): pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_validation.py",
        "class BulkUploadValidator: pass\nclass UploadValidationReport: pass\n"
        "Kafka\nget_async_db_session\n",
    )

    findings = find_upload_component_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "from .ingestion_service import IngestionService",
        "load_workbook",
        "csv.DictReader",
        "def _publish_",
        "Kafka",
        "get_async_db_session",
    ]
