from pathlib import Path

from scripts.upload_component_boundary_guard import (
    find_upload_component_boundary_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_upload_boundary(root: Path) -> None:
    _write(
        root / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "BulkUploadValidator\nUploadRecordPublisher\npublish_records(\n",
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


def test_upload_component_boundary_guard_rejects_monolithic_upload_service(
    tmp_path: Path,
) -> None:
    _write_required_upload_boundary(tmp_path)
    _write(
        tmp_path / "src/services/ingestion_service/app/services/upload_ingestion_service.py",
        "BulkUploadValidator\nUploadRecordPublisher\npublish_records(\n"
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
