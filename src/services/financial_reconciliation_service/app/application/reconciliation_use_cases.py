from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from portfolio_common.domain.tenant import TenantId


class ReconciliationScopeNotFoundError(LookupError):
    """Raised when admitted tenant authority owns no requested reconciliation scope."""


class ReconciliationUnitOfWork(Protocol):
    async def commit(self) -> None: ...


class ReconciliationRunService(Protocol):
    async def run_transaction_cashflow(
        self,
        *,
        request: object,
        tenant_id: TenantId,
        correlation_id: str | None,
    ) -> object: ...

    async def run_position_valuation(
        self,
        *,
        request: object,
        tenant_id: TenantId,
        correlation_id: str | None,
    ) -> object: ...

    async def run_timeseries_integrity(
        self,
        *,
        request: object,
        tenant_id: TenantId,
        correlation_id: str | None,
    ) -> object: ...


class ReconciliationRunRepository(Protocol):
    async def list_runs(
        self,
        *,
        tenant_id: TenantId,
        reconciliation_type: str | None = None,
        portfolio_id: str | None = None,
        limit: int = 50,
    ) -> list[object]: ...

    async def get_run(self, *, tenant_id: TenantId, run_id: str) -> object | None: ...

    async def list_findings(
        self,
        *,
        tenant_id: TenantId,
        run_id: str,
    ) -> list[object]: ...


@dataclass(frozen=True, slots=True)
class ReconciliationRunCommand:
    tenant_id: TenantId
    portfolio_id: str | None
    business_date: date | None
    epoch: int | None
    requested_by: str | None
    tolerance: Decimal | None
    correlation_id: str | None


@dataclass(frozen=True, slots=True)
class ListReconciliationRunsQuery:
    tenant_id: TenantId
    reconciliation_type: str | None
    portfolio_id: str | None
    limit: int


@dataclass(frozen=True, slots=True)
class GetReconciliationRunQuery:
    tenant_id: TenantId
    run_id: str


@dataclass(frozen=True, slots=True)
class ListReconciliationFindingsQuery:
    tenant_id: TenantId
    run_id: str


@dataclass(frozen=True, slots=True)
class ReconciliationRunListResult:
    runs: list[object]
    total: int


@dataclass(frozen=True, slots=True)
class ReconciliationFindingListResult:
    findings: list[object]
    total: int


class ReconciliationUseCases:
    def __init__(
        self,
        *,
        service: ReconciliationRunService,
        repository: ReconciliationRunRepository,
        unit_of_work: ReconciliationUnitOfWork,
    ):
        self._service = service
        self._repository = repository
        self._unit_of_work = unit_of_work

    async def run_transaction_cashflow(
        self,
        command: ReconciliationRunCommand,
    ) -> object:
        run = await self._service.run_transaction_cashflow(
            request=command,
            tenant_id=command.tenant_id,
            correlation_id=command.correlation_id,
        )
        await self._unit_of_work.commit()
        return run

    async def run_position_valuation(
        self,
        command: ReconciliationRunCommand,
    ) -> object:
        run = await self._service.run_position_valuation(
            request=command,
            tenant_id=command.tenant_id,
            correlation_id=command.correlation_id,
        )
        await self._unit_of_work.commit()
        return run

    async def run_timeseries_integrity(
        self,
        command: ReconciliationRunCommand,
    ) -> object:
        run = await self._service.run_timeseries_integrity(
            request=command,
            tenant_id=command.tenant_id,
            correlation_id=command.correlation_id,
        )
        await self._unit_of_work.commit()
        return run

    async def list_runs(
        self,
        query: ListReconciliationRunsQuery,
    ) -> ReconciliationRunListResult:
        runs = await self._repository.list_runs(
            tenant_id=query.tenant_id,
            reconciliation_type=query.reconciliation_type,
            portfolio_id=query.portfolio_id,
            limit=query.limit,
        )
        return ReconciliationRunListResult(runs=runs, total=len(runs))

    async def get_run(
        self,
        query: GetReconciliationRunQuery,
    ) -> object | None:
        return await self._repository.get_run(
            tenant_id=query.tenant_id,
            run_id=query.run_id,
        )

    async def list_findings(
        self,
        query: ListReconciliationFindingsQuery,
    ) -> ReconciliationFindingListResult | None:
        run = await self._repository.get_run(
            tenant_id=query.tenant_id,
            run_id=query.run_id,
        )
        if run is None:
            return None
        findings = await self._repository.list_findings(
            tenant_id=query.tenant_id,
            run_id=query.run_id,
        )
        return ReconciliationFindingListResult(findings=findings, total=len(findings))
