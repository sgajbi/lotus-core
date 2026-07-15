from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from portfolio_common.events import FinancialReconciliationCompletedEvent


class PipelineStageUnitOfWork(Protocol):
    async def claim_event_processing(
        self,
        event_id: str,
        portfolio_id: str,
        service_name: str,
        correlation_id: str | None,
    ) -> bool: ...

    async def register_reconciliation_completed(
        self,
        event: FinancialReconciliationCompletedEvent,
        correlation_id: str | None,
    ) -> None: ...


PipelineStageUnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[PipelineStageUnitOfWork]]


@dataclass(frozen=True)
class PipelineStageHandleResult:
    processed: bool
    duplicate: bool


class PipelineStageMessageHandler:
    def __init__(self, unit_of_work_factory: PipelineStageUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def handle_reconciliation_completed(
        self,
        *,
        event_id: str,
        event: FinancialReconciliationCompletedEvent,
        correlation_id: str | None,
    ) -> PipelineStageHandleResult:
        return await self._handle(
            event_id=event_id,
            portfolio_id=event.portfolio_id,
            service_name="pipeline-orchestrator-reconciliation-completion",
            correlation_id=correlation_id,
            register=lambda uow: uow.register_reconciliation_completed(event, correlation_id),
        )

    async def _handle(
        self,
        *,
        event_id: str,
        portfolio_id: str,
        service_name: str,
        correlation_id: str | None,
        register: Callable[[PipelineStageUnitOfWork], Awaitable[None]],
    ) -> PipelineStageHandleResult:
        async with self._unit_of_work_factory() as unit_of_work:
            claimed = await unit_of_work.claim_event_processing(
                event_id,
                portfolio_id,
                service_name,
                correlation_id,
            )
            if not claimed:
                return PipelineStageHandleResult(processed=False, duplicate=True)
            await register(unit_of_work)
            return PipelineStageHandleResult(processed=True, duplicate=False)
