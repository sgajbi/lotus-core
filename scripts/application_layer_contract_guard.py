from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


APPLICATION_PACKAGE_GLOBS = (
    "src/services/*/app/application",
    "src/services/*/app/use_cases",
)
FORBIDDEN_IMPORT_SNIPPETS = {
    "from fastapi": "application modules must not import FastAPI framework objects",
    "import fastapi": "application modules must not import FastAPI framework objects",
    "from starlette": "application modules must not import Starlette framework objects",
    "import starlette": "application modules must not import Starlette framework objects",
    "from sqlalchemy": "application modules must not import SQLAlchemy infrastructure",
    "import sqlalchemy": "application modules must not import SQLAlchemy infrastructure",
    "KafkaProducer": "application modules must depend on event publisher ports",
    "get_kafka_producer": "application modules must not construct concrete Kafka producers",
    "from ..repositories": "application modules must depend on repository ports",
    "from ..producers": "application modules must depend on publisher ports",
    "from ..consumers": "application modules must not depend on consumer infrastructure",
}


@dataclass(frozen=True, slots=True)
class ApplicationLayerContractFinding:
    path: str
    snippet: str
    reason: str


def _application_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for package_glob in APPLICATION_PACKAGE_GLOBS:
        for package_dir in root.glob(package_glob):
            if package_dir.is_dir():
                files.extend(
                    path for path in package_dir.rglob("*.py") if "__pycache__" not in path.parts
                )
    return sorted(files)


def find_application_layer_contract_findings(
    root: Path,
) -> list[ApplicationLayerContractFinding]:
    findings: list[ApplicationLayerContractFinding] = []
    for source_path in _application_python_files(root):
        source = source_path.read_text(encoding="utf-8")
        relative_path = source_path.relative_to(root).as_posix()
        for snippet, reason in FORBIDDEN_IMPORT_SNIPPETS.items():
            if snippet in source:
                findings.append(
                    ApplicationLayerContractFinding(
                        path=relative_path,
                        snippet=snippet,
                        reason=reason,
                    )
                )
    return findings


def main() -> int:
    findings = find_application_layer_contract_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Application layer contract guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
