from pathlib import Path

from scripts.repository_port_guard import find_repository_port_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_repository_port_guard_allows_repository_ports(tmp_path: Path) -> None:
    _write(
        tmp_path
        / "src/services/financial_reconciliation_service/app/services/reconciliation_service.py",
        "from ..ports.reconciliation_repository_ports import ReconciliationRepositoryPort\n"
        "def __init__(self, repository: ReconciliationRepositoryPort): pass\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/portfolio_tax_lot_window.py",
        "from ..ports.source_data_repository_ports import PortfolioTaxLotReader\n"
        "async def resolve(*, repository: PortfolioTaxLotReader): pass\n",
    )

    assert find_repository_port_findings(tmp_path) == []


def test_repository_port_guard_rejects_broad_concrete_repository_dependencies(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "src/services/financial_reconciliation_service/app/services/reconciliation_service.py",
        "from ..repositories import ReconciliationRepository\n"
        "def __init__(self, repository: ReconciliationRepository, *, timer=None): pass\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/services/portfolio_tax_lot_window.py",
        "async def resolve(*, repository: Any): pass\n",
    )

    findings = find_repository_port_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "from ..repositories import ReconciliationRepository",
        "repository: ReconciliationRepository,",
        "repository: Any",
    ]
