from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_SNIPPETS = {
    "from fastapi import": "ingestion business services must not import FastAPI",
    "import fastapi": "ingestion business services must not import FastAPI",
    "Depends(": "FastAPI dependency providers belong in app/dependencies.py",
    "HTTPException": "HTTP exception mapping belongs in routers or app/dependencies.py",
    "status.HTTP": "HTTP status mapping belongs in routers or app/dependencies.py",
}
SCANNED_PATHS = (
    Path("src/services/ingestion_service/app/adapter_mode.py"),
    Path("src/services/ingestion_service/app/services"),
)


@dataclass(frozen=True, slots=True)
class IngestionFrameworkFinding:
    path: str
    snippet: str
    reason: str


def _candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for relative_path in SCANNED_PATHS:
        path = root / relative_path
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(path.glob("*.py")))
    return files


def find_ingestion_service_framework_findings(root: Path) -> list[IngestionFrameworkFinding]:
    findings: list[IngestionFrameworkFinding] = []
    for path in _candidate_files(root):
        source = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(root).as_posix()
        for snippet, reason in FORBIDDEN_SNIPPETS.items():
            if snippet in source:
                findings.append(
                    IngestionFrameworkFinding(
                        path=relative_path,
                        snippet=snippet,
                        reason=reason,
                    )
                )
    return findings


def main() -> int:
    findings = find_ingestion_service_framework_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Ingestion service framework guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
