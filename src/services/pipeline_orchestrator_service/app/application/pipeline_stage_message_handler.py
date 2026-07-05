from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from portfolio_common.events import (
    CashflowCalculatedEvent,
    FinancialReconciliationCompletedEvent,
    PortfolioAggregationDayCompletedEvent,
    TransactionEvent,
)


class PipelineStageUnitOfWork(Protocol):
    async def __aenter__(self) -> PipelineStageUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    async def claim_event_processing(
        self,
        event_id: str,
        portfolio_id: str,
        service_name: str,
        correlation_id: str | None,
    ) -> bool: ...

    async def register_processed_transaction(
        self,
        event: TransactionEvent,
        correlation_id: str | None,
    ) -> None: ...

    async def register_cashflow_calculated(
        self,
        event: CashflowCalculatedEvent,
        correlation_id: str | None,
    ) -> None: ...

    async def register_portfolio_aggregation_completed(
        self,
        event: PortfolioAggregationDayCompletedEvent,
        correlation_id: str | None,
    ) -> None: ...

    async def register_reconciliation_completed(
        self,
        event: FinancialReconciliationCompletedEvent,
        correlation_id: str | None,
    ) -> None: ...


PipelineStageUnitOfWorkFactory = Callable[[], PipelineStageUnitOfWork]


@dataclass(frozen=True)
class PipelineStageHandleResult:
    processed: bool
    duplicate: bool


class PipelineStageMessageHandler:
    def __init__(self, unit_of_work_factory: PipelineStageUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def handle_processed_transaction(
        self,
        *,
        event_id: str,
        event: TransactionEvent,
        correlation_id: str | None,
    ) -> PipelineStageHandleResult:
        return await self._handle(
            event_id=event_id,
            portfolio_id=event.portfolio_id,
            service_name="pipeline-orchestrator-processed-txn",
            correlation_id=correlation_id,
            register=lambda uow: uow.register_processed_transaction(event, correlation_id),
        )

    async def handle_cashflow_calculated(
        self,
        *,
        event_id: str,
        event: CashflowCalculatedEvent,
        correlation_id: str | None,
    ) -> PipelineStageHandleResult:
        return await self._handle(
            event_id=event_id,
            portfolio_id=event.portfolio_id,
            service_name="pipeline-orchestrator-cashflow",
            correlation_id=correlation_id,
            register=lambda uow: uow.register_cashflow_calculated(event, correlation_id),
        )

    async def handle_portfolio_aggregation_completed(
        self,
        *,
        event_id: str,
        event: PortfolioAggregationDayCompletedEvent,
        correlation_id: str | None,
    ) -> PipelineStageHandleResult:
        return await self._handle(
            event_id=event_id,
            portfolio_id=event.portfolio_id,
            service_name="pipeline-orchestrator-portfolio-aggregation",
            correlation_id=correlation_id,
            register=lambda uow: uow.register_portfolio_aggregation_completed(
                event,
                correlation_id,
            ),
        )

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
