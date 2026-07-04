from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from src.services.financial_reconciliation_service.app.application import (
    GetReconciliationRunQuery,
    ListReconciliationFindingsQuery,
    ListReconciliationRunsQuery,
    ReconciliationRunCommand,
    ReconciliationUseCases,
)


@dataclass
class FakeUnitOfWork:
    commit_count: int = 0

    async def commit(self) -> None:
        self.commit_count += 1


@dataclass
class FakeReconciliationService:
    returned_run: object
    calls: list[tuple[str, object, str | None]] = field(default_factory=list)

    async def run_transaction_cashflow(
        self,
        *,
        request: object,
        correlation_id: str | None,
    ) -> object:
        self.calls.append(("transaction_cashflow", request, correlation_id))
        return self.returned_run

    async def run_position_valuation(
        self,
        *,
        request: object,
        correlation_id: str | None,
    ) -> object:
        self.calls.append(("position_valuation", request, correlation_id))
        return self.returned_run

    async def run_timeseries_integrity(
        self,
        *,
        request: object,
        correlation_id: str | None,
    ) -> object:
        self.calls.append(("timeseries_integrity", request, correlation_id))
        return self.returned_run


@dataclass
class FakeReconciliationRepository:
    runs: list[object] = field(default_factory=list)
    run_by_id: dict[str, object] = field(default_factory=dict)
    findings_by_run_id: dict[str, list[object]] = field(default_factory=dict)
    list_runs_calls: list[tuple[str | None, str | None, int]] = field(default_factory=list)

    async def list_runs(
        self,
        *,
        reconciliation_type: str | None = None,
        portfolio_id: str | None = None,
        limit: int = 50,
    ) -> list[object]:
        self.list_runs_calls.append((reconciliation_type, portfolio_id, limit))
        return self.runs

    async def get_run(self, run_id: str) -> object | None:
        return self.run_by_id.get(run_id)

    async def list_findings(self, run_id: str) -> list[object]:
        return self.findings_by_run_id.get(run_id, [])


def _use_cases(
    *,
    service: FakeReconciliationService | None = None,
    repository: FakeReconciliationRepository | None = None,
    unit_of_work: FakeUnitOfWork | None = None,
) -> tuple[
    ReconciliationUseCases,
    FakeReconciliationService,
    FakeReconciliationRepository,
    FakeUnitOfWork,
]:
    fake_service = service or FakeReconciliationService(
        returned_run=SimpleNamespace(run_id="run-1")
    )
    fake_repository = repository or FakeReconciliationRepository()
    fake_unit_of_work = unit_of_work or FakeUnitOfWork()
    return (
        ReconciliationUseCases(
            service=fake_service,
            repository=fake_repository,
            unit_of_work=fake_unit_of_work,
        ),
        fake_service,
        fake_repository,
        fake_unit_of_work,
    )


@pytest.mark.asyncio
async def test_run_transaction_cashflow_commits_after_service_call() -> None:
    command = ReconciliationRunCommand(
        portfolio_id="P1",
        business_date=None,
        epoch=None,
        requested_by="ops",
        tolerance=None,
        correlation_id="corr-1",
    )
    use_cases, service, _, unit_of_work = _use_cases()

    run = await use_cases.run_transaction_cashflow(command)

    assert run.run_id == "run-1"
    assert service.calls == [("transaction_cashflow", command, "corr-1")]
    assert unit_of_work.commit_count == 1


@pytest.mark.asyncio
async def test_run_position_valuation_commits_after_service_call() -> None:
    command = ReconciliationRunCommand(
        portfolio_id="P1",
        business_date=None,
        epoch=None,
        requested_by=None,
        tolerance=None,
        correlation_id=None,
    )
    use_cases, service, _, unit_of_work = _use_cases()

    await use_cases.run_position_valuation(command)

    assert service.calls == [("position_valuation", command, None)]
    assert unit_of_work.commit_count == 1


@pytest.mark.asyncio
async def test_run_timeseries_integrity_commits_after_service_call() -> None:
    command = ReconciliationRunCommand(
        portfolio_id="P1",
        business_date=None,
        epoch=None,
        requested_by=None,
        tolerance=None,
        correlation_id="corr-2",
    )
    use_cases, service, _, unit_of_work = _use_cases()

    await use_cases.run_timeseries_integrity(command)

    assert service.calls == [("timeseries_integrity", command, "corr-2")]
    assert unit_of_work.commit_count == 1


@pytest.mark.asyncio
async def test_list_runs_returns_query_result_without_commit() -> None:
    repository = FakeReconciliationRepository(runs=[SimpleNamespace(run_id="run-1")])
    use_cases, _, _, unit_of_work = _use_cases(repository=repository)

    result = await use_cases.list_runs(
        ListReconciliationRunsQuery(
            reconciliation_type="transaction_cashflow",
            portfolio_id="P1",
            limit=25,
        )
    )

    assert result.runs == repository.runs
    assert result.total == 1
    assert repository.list_runs_calls == [("transaction_cashflow", "P1", 25)]
    assert unit_of_work.commit_count == 0


@pytest.mark.asyncio
async def test_get_run_returns_optional_result() -> None:
    expected_run = SimpleNamespace(run_id="run-1")
    repository = FakeReconciliationRepository(run_by_id={"run-1": expected_run})
    use_cases, _, _, _ = _use_cases(repository=repository)

    assert await use_cases.get_run(GetReconciliationRunQuery(run_id="run-1")) is expected_run
    assert await use_cases.get_run(GetReconciliationRunQuery(run_id="missing")) is None


@pytest.mark.asyncio
async def test_list_findings_requires_existing_run() -> None:
    findings = [SimpleNamespace(finding_id="finding-1")]
    repository = FakeReconciliationRepository(
        run_by_id={"run-1": SimpleNamespace(run_id="run-1")},
        findings_by_run_id={"run-1": findings},
    )
    use_cases, _, _, _ = _use_cases(repository=repository)

    result = await use_cases.list_findings(ListReconciliationFindingsQuery(run_id="run-1"))
    missing = await use_cases.list_findings(ListReconciliationFindingsQuery(run_id="missing"))

    assert result is not None
    assert result.findings == findings
    assert result.total == 1
    assert missing is None
