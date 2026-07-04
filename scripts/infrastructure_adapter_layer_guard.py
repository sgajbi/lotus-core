from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REQUIRED_INFRASTRUCTURE_MODULES = (
    Path("src/services/ingestion_service/app/infrastructure/__init__.py"),
    Path("src/services/ingestion_service/app/infrastructure/workflow_stores.py"),
)
TRANSITIONAL_COMPATIBILITY_MODULE = Path(
    "src/services/ingestion_service/app/adapters/ingestion_workflow_stores.py"
)
FORBIDDEN_APPLICATION_SNIPPETS = {
    Path("src/services/ingestion_service/app/services/ingestion_job_service.py"): {
        "from ..adapters.ingestion_workflow_stores import": (
            "application services must import migrated concrete stores from app.infrastructure"
        ),
    },
}
FORBIDDEN_COMPATIBILITY_SNIPPETS = {
    "class SqlAlchemyIngestionJobStore": (
        "transitional adapter module must re-export the infrastructure implementation"
    ),
    "class SqlAlchemyReplayAuditStore": (
        "transitional adapter module must re-export the infrastructure implementation"
    ),
    "create_or_get_job_result(": (
        "transitional adapter module must not retain SQLAlchemy helper wiring"
    ),
}


@dataclass(frozen=True, slots=True)
class InfrastructureAdapterLayerFinding:
    path: str
    snippet: str
    reason: str


def find_infrastructure_adapter_layer_findings(
    root: Path,
) -> list[InfrastructureAdapterLayerFinding]:
    findings: list[InfrastructureAdapterLayerFinding] = []

    for relative_path in REQUIRED_INFRASTRUCTURE_MODULES:
        if not (root / relative_path).exists():
            findings.append(
                InfrastructureAdapterLayerFinding(
                    path=relative_path.as_posix(),
                    snippet="<missing-file>",
                    reason="required infrastructure adapter module is missing",
                )
            )

    for relative_path, snippets in FORBIDDEN_APPLICATION_SNIPPETS.items():
        path = root / relative_path
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for snippet, reason in snippets.items():
            if snippet in source:
                findings.append(
                    InfrastructureAdapterLayerFinding(
                        path=relative_path.as_posix(),
                        snippet=snippet,
                        reason=reason,
                    )
                )

    compatibility_path = root / TRANSITIONAL_COMPATIBILITY_MODULE
    if compatibility_path.exists():
        compatibility_source = compatibility_path.read_text(encoding="utf-8")
        if "from ..infrastructure.workflow_stores import" not in compatibility_source:
            findings.append(
                InfrastructureAdapterLayerFinding(
                    path=TRANSITIONAL_COMPATIBILITY_MODULE.as_posix(),
                    snippet="<missing-re-export>",
                    reason="transitional adapter module must re-export infrastructure stores",
                )
            )
        for snippet, reason in FORBIDDEN_COMPATIBILITY_SNIPPETS.items():
            if snippet in compatibility_source:
                findings.append(
                    InfrastructureAdapterLayerFinding(
                        path=TRANSITIONAL_COMPATIBILITY_MODULE.as_posix(),
                        snippet=snippet,
                        reason=reason,
                    )
                )

    return findings


def main() -> int:
    findings = find_infrastructure_adapter_layer_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Infrastructure adapter layer guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
