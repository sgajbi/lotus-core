from pathlib import Path

from scripts.application_dependency_inversion_guard import (
    find_application_dependency_inversion_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_application_dependency_inversion_guard_allows_port_enabled_modules(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "from ..ports.ingestion_workflow_stores import IngestionJobStore\n"
        "await self._job_store.create_or_get_job(command)\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_service.py",
        "from portfolio_common.event_publisher import EventPublisher\n"
        "class IngestionService:\n"
        "    def __init__(self, event_publisher: EventPublisher): pass\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/portfolio_tax_lot_window.py",
        "from ..ports.source_data_repository_ports import PortfolioTaxLotReader\n"
        "async def resolve(*, repository: PortfolioTaxLotReader): pass\n",
    )
    _write(
        tmp_path
        / "src/services/financial_reconciliation_service/app/services/reconciliation_service.py",
        "from ..ports.reconciliation_repository_ports import ReconciliationRepositoryPort\n"
        "class ReconciliationService:\n"
        "    def __init__(self, repository: ReconciliationRepositoryPort): pass\n",
    )

    assert find_application_dependency_inversion_findings(tmp_path) == []


def test_application_dependency_inversion_guard_rejects_concrete_dependencies(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "from sqlalchemy.ext.asyncio import AsyncSession\n"
        "await create_or_get_job_result(session_factory=session_factory)\n"
        "await record_consumer_dlq_replay_audit_response(session_factory=session_factory)\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_service.py",
        "from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/portfolio_tax_lot_window.py",
        "from ..repositories import ReferenceDataRepository, TransactionRepository\n"
        "async def resolve(*, repository: Any): pass\n",
    )
    _write(
        tmp_path
        / "src/services/financial_reconciliation_service/app/services/reconciliation_service.py",
        "from ..repositories import ReconciliationRepository\n"
        "class ReconciliationService:\n"
        "    def __init__(self, repository: ReconciliationRepository,): pass\n",
    )

    findings = find_application_dependency_inversion_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "from sqlalchemy.ext.asyncio import AsyncSession",
        "create_or_get_job_result(",
        "record_consumer_dlq_replay_audit_response(",
        "portfolio_common.kafka_utils",
        "KafkaProducer",
        "get_kafka_producer",
        "from ..repositories import",
        "ReferenceDataRepository",
        "TransactionRepository",
        "repository: Any",
        "from ..repositories import ReconciliationRepository",
        "repository: ReconciliationRepository,",
    ]
