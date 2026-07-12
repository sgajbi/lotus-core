from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STANDARD_PATH = Path("docs/standards/api-mapper-pattern-standard.md")
REQUIRED_SNIPPETS = {
    Path("src/services/query_service/app/routers/lookup_mappers.py"): (
        "def lookup_response_from_result",
        "LookupCatalogResult",
        "LookupResponse",
    ),
    Path("src/services/query_service/app/routers/lookups.py"): (
        "from .lookup_mappers import lookup_response_from_result",
    ),
    Path("src/services/financial_reconciliation_service/app/routers/reconciliation_mappers.py"): (
        "def reconciliation_run_command_from_request",
        "def reconciliation_run_not_found",
        "ReconciliationRunCommand",
    ),
    Path("src/services/financial_reconciliation_service/app/routers/reconciliation.py"): (
        "reconciliation_run_command_from_request",
        "reconciliation_run_not_found",
    ),
    Path("src/services/event_replay_service/app/routers/replay_mappers.py"): (
        "def command_error_to_http",
        "HTTPException",
    ),
    Path("src/services/event_replay_service/app/routers/ingestion_operations.py"): (
        "from .replay_mappers import command_error_to_http",
    ),
    Path("src/services/query_service/app/routers/http_errors.py"): (
        "def lookup_error_to_http",
        "def value_error_to_http",
        "def value_error_as_resolution_http",
    ),
}
FORBIDDEN_SNIPPETS = {
    Path("src/services/query_service/app/routers/lookups.py"): ("def lookup_response_from_result",),
    Path("src/services/financial_reconciliation_service/app/routers/reconciliation.py"): (
        "def _reconciliation_run_not_found",
        "ReconciliationRunCommand(",
    ),
    Path("src/services/event_replay_service/app/routers/ingestion_operations.py"): (
        "HTTPException(status_code=exc.status_code, detail=exc.detail)",
    ),
    Path("src/services/query_service/app/routers/buy_state.py"): (
        "HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))",
    ),
    Path("src/services/query_service/app/routers/cash_accounts.py"): (
        "HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))",
    ),
    Path("src/services/query_service/app/routers/cash_movements.py"): (
        "HTTPException(status_code=status_code, detail=detail)",
    ),
    Path("src/services/query_service/app/routers/positions.py"): (
        "HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))",
    ),
    Path("src/services/query_service/app/routers/reporting.py"): (
        "HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))",
        "HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))",
    ),
    Path("src/services/query_service/app/routers/sell_state.py"): (
        "HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))",
    ),
    Path("src/services/query_service/app/routers/transactions.py"): (
        "HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))",
        "HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))",
    ),
}


@dataclass(frozen=True, slots=True)
class ApiMapperPatternFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def find_api_mapper_pattern_findings(root: Path) -> list[ApiMapperPatternFinding]:
    findings: list[ApiMapperPatternFinding] = []
    if not (root / STANDARD_PATH).exists():
        findings.append(
            ApiMapperPatternFinding(
                path=STANDARD_PATH.as_posix(),
                rule="missing-api-mapper-standard",
                detail="API mapper pattern standard is missing",
            )
        )
    for relative_path, snippets in REQUIRED_SNIPPETS.items():
        path = root / relative_path
        if not path.exists():
            findings.append(
                ApiMapperPatternFinding(
                    path=relative_path.as_posix(),
                    rule="missing-api-mapper-artifact",
                    detail="required representative API mapper artifact is missing",
                )
            )
            continue
        source = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in source:
                findings.append(
                    ApiMapperPatternFinding(
                        path=relative_path.as_posix(),
                        rule="missing-api-mapper-snippet",
                        detail=f"missing required snippet: {snippet}",
                    )
                )
    for relative_path, snippets in FORBIDDEN_SNIPPETS.items():
        path = root / relative_path
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet in source:
                findings.append(
                    ApiMapperPatternFinding(
                        path=relative_path.as_posix(),
                        rule="forbidden-router-mapping-snippet",
                        detail=f"forbidden router-local mapping snippet remains: {snippet}",
                    )
                )
    return findings


def main() -> int:
    findings = find_api_mapper_pattern_findings(Path.cwd())
    if findings:
        print("API mapper pattern guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("API mapper pattern guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
