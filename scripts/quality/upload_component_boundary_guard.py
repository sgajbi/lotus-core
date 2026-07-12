from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SERVICE_PATH = Path("src/services/ingestion_service/app/services/upload_ingestion_service.py")
VALIDATOR_PATH = Path("src/services/ingestion_service/app/services/upload_validation.py")
PUBLISHER_PATH = Path("src/services/ingestion_service/app/services/upload_publishers.py")
PORT_PATH = Path("src/services/ingestion_service/app/ports/upload_record_publisher.py")

FORBIDDEN_SERVICE_SNIPPETS = {
    "from .ingestion_service import IngestionService": (
        "upload use case must depend on UploadRecordPublisher, not concrete ingestion service"
    ),
    "load_workbook": "upload parsing belongs in upload_validation.py",
    "csv.DictReader": "upload parsing belongs in upload_validation.py",
    "def _publish_": "entity publish dispatch belongs in upload_publishers.py",
}
FORBIDDEN_VALIDATOR_SNIPPETS = {
    "fastapi": "upload validator must not depend on HTTP framework objects",
    "Kafka": "upload validator must not depend on Kafka or publisher adapters",
    "get_async_db_session": "upload validator must not depend on database sessions",
    "IngestionService": "upload validator must not depend on ingestion service publication",
}
REQUIRED_SNIPPETS = {
    SERVICE_PATH: (
        "BulkUploadValidator",
        "UploadRecordPublisher",
        "publish_records(",
    ),
    VALIDATOR_PATH: (
        "class BulkUploadValidator",
        "class UploadValidationReport",
    ),
    PUBLISHER_PATH: (
        "class IngestionServiceUploadPublisher",
        "UploadRecordPublisher",
    ),
    PORT_PATH: (
        "class UploadRecordPublisher",
        "async def publish_records",
    ),
}


@dataclass(frozen=True, slots=True)
class UploadBoundaryFinding:
    path: str
    snippet: str
    reason: str


def find_upload_component_boundary_findings(root: Path) -> list[UploadBoundaryFinding]:
    findings: list[UploadBoundaryFinding] = []
    for relative_path, snippets in REQUIRED_SNIPPETS.items():
        path = root / relative_path
        if not path.exists():
            findings.append(
                UploadBoundaryFinding(
                    path=relative_path.as_posix(),
                    snippet="<missing-file>",
                    reason="required upload component boundary file is missing",
                )
            )
            continue
        source = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in source:
                findings.append(
                    UploadBoundaryFinding(
                        path=relative_path.as_posix(),
                        snippet=snippet,
                        reason="required upload component boundary snippet is missing",
                    )
                )

    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=SERVICE_PATH,
            snippets=FORBIDDEN_SERVICE_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=VALIDATOR_PATH,
            snippets=FORBIDDEN_VALIDATOR_SNIPPETS,
        )
    )
    return findings


def _forbidden_snippet_findings(
    *,
    root: Path,
    relative_path: Path,
    snippets: dict[str, str],
) -> list[UploadBoundaryFinding]:
    path = root / relative_path
    if not path.exists():
        return []
    source = path.read_text(encoding="utf-8")
    return [
        UploadBoundaryFinding(
            path=relative_path.as_posix(),
            snippet=snippet,
            reason=reason,
        )
        for snippet, reason in snippets.items()
        if snippet in source
    ]


def main() -> int:
    findings = find_upload_component_boundary_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Upload component boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
