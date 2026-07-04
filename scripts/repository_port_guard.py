from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


FORBIDDEN_SNIPPETS = {
    Path("src/services/financial_reconciliation_service/app/services/reconciliation_service.py"): {
        "from ..repositories import ReconciliationRepository": (
            "reconciliation services must depend on reconciliation repository ports"
        ),
        "repository: ReconciliationRepository,": (
            "reconciliation service constructor must use ReconciliationRepositoryPort"
        ),
    },
    Path("src/services/query_service/app/services/portfolio_tax_lot_window.py"): {
        "repository: Any": "portfolio tax-lot source-data use case must use PortfolioTaxLotReader",
    },
}


@dataclass(frozen=True, slots=True)
class RepositoryPortFinding:
    path: str
    snippet: str
    reason: str


def find_repository_port_findings(root: Path) -> list[RepositoryPortFinding]:
    findings: list[RepositoryPortFinding] = []
    for relative_path, snippets in FORBIDDEN_SNIPPETS.items():
        path = root / relative_path
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for snippet, reason in snippets.items():
            if snippet in source:
                findings.append(
                    RepositoryPortFinding(
                        path=relative_path.as_posix(),
                        snippet=snippet,
                        reason=reason,
                    )
                )
    return findings


def main() -> int:
    findings = find_repository_port_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Repository port guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
