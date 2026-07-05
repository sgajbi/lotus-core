from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REQUIRED_MODULE_SYMBOLS = {
    Path("src/services/ingestion_service/app/application/upload_commands.py"): (
        "class UploadPreviewCommand",
        "class UploadCommitCommand",
        "class UploadPreviewResult",
        "class UploadCommitResult",
    ),
    Path("src/services/query_service/app/application/lookup_catalog.py"): (
        "class PortfolioLookupQuery",
        "class InstrumentLookupQuery",
        "class CurrencyLookupQuery",
        "class LookupCatalogResult",
    ),
    Path("src/services/query_service/app/application/core_snapshot.py"): (
        "class CoreSnapshotIdentityCommand",
        "class CoreSnapshotOptionsCommand",
        "class CoreSnapshotSimulationCommand",
    ),
}
FORBIDDEN_SERVICE_SNIPPETS = {
    Path("src/services/ingestion_service/app/services/upload_ingestion_service.py"): {
        "..DTOs.upload_dto": "upload use case must not depend on upload API DTO contracts",
        "UploadPreviewResponse": "upload use case must return application results",
        "UploadCommitResponse": "upload use case must return application results",
        "UploadRowError": "upload validation issues must use application result models",
    },
    Path("src/services/query_service/app/services/lookup_catalog_service.py"): {
        "..dtos.lookup_dto": "lookup use case must not depend on lookup API DTO contracts",
        "LookupResponse": "lookup use case must return application results",
        "LookupItem": "lookup use case must use application result items",
    },
    Path("src/services/query_service/app/services/core_snapshot_service.py"): {
        'request.model_dump(mode="json")': (
            "core snapshot fingerprinting must use canonical application command payloads"
        ),
    },
}
REQUIRED_SERVICE_SNIPPETS = {
    Path("src/services/ingestion_service/app/services/upload_ingestion_service.py"): (
        "UploadPreviewCommand",
        "UploadCommitCommand",
        "UploadPreviewResult",
        "UploadCommitResult",
    ),
    Path("src/services/query_service/app/services/lookup_catalog_service.py"): (
        "PortfolioLookupQuery",
        "InstrumentLookupQuery",
        "CurrencyLookupQuery",
        "LookupCatalogResult",
    ),
    Path("src/services/query_service/app/services/core_snapshot_service.py"): (
        "CoreSnapshotIdentityCommand",
        "canonical_payload()",
    ),
}


@dataclass(frozen=True, slots=True)
class ApplicationCommandResultFinding:
    path: str
    snippet: str
    reason: str


def find_application_command_result_findings(
    root: Path,
) -> list[ApplicationCommandResultFinding]:
    findings: list[ApplicationCommandResultFinding] = []

    for module_path, snippets in REQUIRED_MODULE_SYMBOLS.items():
        source_path = root / module_path
        if not source_path.exists():
            findings.append(
                ApplicationCommandResultFinding(
                    path=module_path.as_posix(),
                    snippet="<missing-file>",
                    reason="application command/result module is missing",
                )
            )
            continue
        source = source_path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in source:
                findings.append(
                    ApplicationCommandResultFinding(
                        path=module_path.as_posix(),
                        snippet=snippet,
                        reason="application command/result symbol is required",
                    )
                )

    for service_path, snippets in REQUIRED_SERVICE_SNIPPETS.items():
        source_path = root / service_path
        if not source_path.exists():
            findings.append(
                ApplicationCommandResultFinding(
                    path=service_path.as_posix(),
                    snippet="<missing-file>",
                    reason="representative application service is missing",
                )
            )
            continue
        source = source_path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in source:
                findings.append(
                    ApplicationCommandResultFinding(
                        path=service_path.as_posix(),
                        snippet=snippet,
                        reason="representative service must use application command/result models",
                    )
                )
        for snippet, reason in FORBIDDEN_SERVICE_SNIPPETS[service_path].items():
            if snippet in source:
                findings.append(
                    ApplicationCommandResultFinding(
                        path=service_path.as_posix(),
                        snippet=snippet,
                        reason=reason,
                    )
                )

    return findings


def main() -> int:
    findings = find_application_command_result_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Application command/result guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
