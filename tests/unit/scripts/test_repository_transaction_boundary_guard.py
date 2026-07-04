from pathlib import Path

from scripts.repository_transaction_boundary_guard import (
    find_repository_transaction_boundary_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_repository_transaction_boundary_guard_allows_staged_repository(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/query_service/app/repositories/simulation_repository.py",
        "class SimulationRepository:\n"
        "    async def create_session(self):\n"
        "        self.db.add(object())\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/repositories/operations_repository.py",
        "class OperationsRepository:\n"
        "    async def update_status(self):\n"
        "        await self.db.commit()\n",
    )

    assert find_repository_transaction_boundary_findings(tmp_path) == []


def test_repository_transaction_boundary_guard_rejects_unclassified_transactions(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/query_service/app/repositories/simulation_repository.py",
        "class SimulationRepository:\n"
        "    async def create_session(self):\n"
        "        await self.db.commit()\n"
        "    async def abandon(self):\n"
        "        await self.db.rollback()\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/repositories/operations_repository.py",
        "class OperationsRepository:\n"
        "    async def update_status(self):\n"
        "        await self.db.commit()\n",
    )

    findings = find_repository_transaction_boundary_findings(tmp_path)

    assert [(finding.path, finding.token) for finding in findings] == [
        (
            "src/services/query_service/app/repositories/simulation_repository.py",
            "commit(",
        ),
        (
            "src/services/query_service/app/repositories/simulation_repository.py",
            "rollback(",
        ),
    ]


def test_repository_transaction_boundary_guard_rejects_stale_exception(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/query_service/app/repositories/operations_repository.py",
        "class OperationsRepository:\n"
        "    async def update_status(self):\n"
        "        self.db.add(object())\n",
    )

    findings = find_repository_transaction_boundary_findings(tmp_path)

    assert findings[0].path == (
        "src/services/query_service/app/repositories/operations_repository.py"
    )
    assert findings[0].token == "<stale-exception>"


def test_repository_transaction_boundary_guard_ignores_generated_build_copies(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/query_service/build/lib/app/repositories/simulation_repository.py",
        "class SimulationRepository:\n"
        "    async def create_session(self):\n"
        "        await self.db.commit()\n",
    )
    _write(
        tmp_path / "src/services/query_service/app/repositories/operations_repository.py",
        "class OperationsRepository:\n"
        "    async def update_status(self):\n"
        "        await self.db.commit()\n",
    )

    assert find_repository_transaction_boundary_findings(tmp_path) == []
