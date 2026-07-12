from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_DEPENDENCY_SNIPPETS = {
    Path("src/services/ingestion_service/app/services/ingestion_job_service.py"): {
        "from sqlalchemy.ext.asyncio import AsyncSession": (
            "ingestion job workflows must use store ports at the application boundary"
        ),
        "create_or_get_job_result(": "job creation and idempotency must use IngestionJobStore",
        "record_consumer_dlq_replay_audit_response(": (
            "replay audit writes must use ReplayAuditStore"
        ),
        "find_successful_replay_audit_by_fingerprint_response(": (
            "replay audit duplicate checks must use ReplayAuditStore"
        ),
    },
    Path("src/services/ingestion_service/app/services/ingestion_service.py"): {
        "portfolio_common.kafka_utils": (
            "ingestion publishing must use portfolio_common.event_publisher"
        ),
        "KafkaProducer": "ingestion publishing must use the EventPublisher port",
        "get_kafka_producer": "runtime composition must own concrete Kafka publisher creation",
    },
    Path("src/services/query_service/app/services/portfolio_tax_lot_window.py"): {
        "from sqlalchemy.ext.asyncio import AsyncSession": (
            "PortfolioTaxLotWindow:v1 must use PortfolioTaxLotReader"
        ),
        "from ..repositories import": (
            "PortfolioTaxLotWindow:v1 must not import broad concrete repositories"
        ),
        "ReferenceDataRepository": (
            "PortfolioTaxLotWindow:v1 must use a capability-specific reader port"
        ),
        "TransactionRepository": (
            "PortfolioTaxLotWindow:v1 must use a capability-specific reader port"
        ),
        "PortfolioRepository": (
            "PortfolioTaxLotWindow:v1 must use a capability-specific reader port"
        ),
        "repository: Any": ("PortfolioTaxLotWindow:v1 must depend on PortfolioTaxLotReader"),
    },
    Path("src/services/financial_reconciliation_service/app/services/reconciliation_service.py"): {
        "from sqlalchemy.ext.asyncio import AsyncSession": (
            "reconciliation orchestration must use repository ports"
        ),
        "from ..repositories import ReconciliationRepository": (
            "reconciliation orchestration must depend on ReconciliationRepositoryPort"
        ),
        "repository: ReconciliationRepository,": (
            "reconciliation constructor must use ReconciliationRepositoryPort"
        ),
    },
}


@dataclass(frozen=True, slots=True)
class ApplicationDependencyInversionFinding:
    path: str
    snippet: str
    reason: str


def find_application_dependency_inversion_findings(
    root: Path,
) -> list[ApplicationDependencyInversionFinding]:
    findings: list[ApplicationDependencyInversionFinding] = []
    for relative_path, snippets in FORBIDDEN_DEPENDENCY_SNIPPETS.items():
        path = root / relative_path
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for snippet, reason in snippets.items():
            if snippet in source:
                findings.append(
                    ApplicationDependencyInversionFinding(
                        path=relative_path.as_posix(),
                        snippet=snippet,
                        reason=reason,
                    )
                )
    return findings


def main() -> int:
    findings = find_application_dependency_inversion_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Application dependency inversion guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
