from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ERROR_TAXONOMY_MODULE = Path("src/services/ingestion_service/app/application/errors.py")
UPLOAD_APPLICATION_SERVICE = Path(
    "src/services/ingestion_service/app/services/upload_ingestion_service.py"
)
REQUIRED_ERROR_SYMBOLS = (
    "class ApplicationError",
    "class ValidationRejected",
    "class UnsupportedOperation",
)
REQUIRED_UPLOAD_SNIPPETS = (
    "ValidationRejected",
    "UnsupportedOperation",
)
FORBIDDEN_UPLOAD_SNIPPETS = {
    "HTTPException": "application services must raise application errors, not HTTP exceptions",
    "status.HTTP_": "HTTP status mapping belongs in the API router",
    "from fastapi": "FastAPI dependency wiring belongs outside application services",
}


@dataclass(frozen=True, slots=True)
class ApplicationErrorTaxonomyFinding:
    path: str
    snippet: str
    reason: str


def find_application_error_taxonomy_findings(
    root: Path,
) -> list[ApplicationErrorTaxonomyFinding]:
    findings: list[ApplicationErrorTaxonomyFinding] = []

    taxonomy_path = root / ERROR_TAXONOMY_MODULE
    if not taxonomy_path.exists():
        findings.append(
            ApplicationErrorTaxonomyFinding(
                path=ERROR_TAXONOMY_MODULE.as_posix(),
                snippet="<missing-file>",
                reason="application error taxonomy module is missing",
            )
        )
    else:
        taxonomy_source = taxonomy_path.read_text(encoding="utf-8")
        for snippet in REQUIRED_ERROR_SYMBOLS:
            if snippet not in taxonomy_source:
                findings.append(
                    ApplicationErrorTaxonomyFinding(
                        path=ERROR_TAXONOMY_MODULE.as_posix(),
                        snippet=snippet,
                        reason="application error taxonomy symbol is required",
                    )
                )

    service_path = root / UPLOAD_APPLICATION_SERVICE
    if not service_path.exists():
        findings.append(
            ApplicationErrorTaxonomyFinding(
                path=UPLOAD_APPLICATION_SERVICE.as_posix(),
                snippet="<missing-file>",
                reason="upload application service module is missing",
            )
        )
        return findings

    service_source = service_path.read_text(encoding="utf-8")
    for snippet in REQUIRED_UPLOAD_SNIPPETS:
        if snippet not in service_source:
            findings.append(
                ApplicationErrorTaxonomyFinding(
                    path=UPLOAD_APPLICATION_SERVICE.as_posix(),
                    snippet=snippet,
                    reason="upload service must use framework-independent application errors",
                )
            )
    for snippet, reason in FORBIDDEN_UPLOAD_SNIPPETS.items():
        if snippet in service_source:
            findings.append(
                ApplicationErrorTaxonomyFinding(
                    path=UPLOAD_APPLICATION_SERVICE.as_posix(),
                    snippet=snippet,
                    reason=reason,
                )
            )

    return findings


def main() -> int:
    findings = find_application_error_taxonomy_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Application error taxonomy guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
