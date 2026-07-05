from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from portfolio_common.db import get_async_db_session
from portfolio_common.events import (
    CashflowCalculatedEvent,
    FinancialReconciliationCompletedEvent,
    PortfolioAggregationDayCompletedEvent,
    TransactionEvent,
)
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.pipeline_stage_repository import PipelineStageRepository
from ..services.pipeline_orchestrator_service import PipelineOrchestratorService


class SqlAlchemyPipelineStageUnitOfWork:
    def __init__(self, db: AsyncSession) -> None:
        self._idempotency_repo = IdempotencyRepository(db)
        self._service = PipelineOrchestratorService(
            repo=PipelineStageRepository(db),
            outbox_repo=OutboxRepository(db),
        )

    async def claim_event_processing(
        self,
        event_id: str,
        portfolio_id: str,
        service_name: str,
        correlation_id: str | None,
    ) -> bool:
        return await self._idempotency_repo.claim_event_processing(
            event_id,
            portfolio_id,
            service_name,
            correlation_id,
        )

    async def register_processed_transaction(
        self,
        event: TransactionEvent,
        correlation_id: str | None,
    ) -> None:
        await self._service.register_processed_transaction(event, correlation_id)

    async def register_cashflow_calculated(
        self,
        event: CashflowCalculatedEvent,
        correlation_id: str | None,
    ) -> None:
        await self._service.register_cashflow_calculated(event, correlation_id)

    async def register_portfolio_aggregation_completed(
        self,
        event: PortfolioAggregationDayCompletedEvent,
        correlation_id: str | None,
    ) -> None:
        await self._service.register_portfolio_aggregation_completed(event, correlation_id)

    async def register_reconciliation_completed(
        self,
        event: FinancialReconciliationCompletedEvent,
        correlation_id: str | None,
    ) -> None:
        await self._service.register_reconciliation_completed(event, correlation_id)


@asynccontextmanager
async def sqlalchemy_pipeline_stage_unit_of_work() -> AsyncIterator[
    SqlAlchemyPipelineStageUnitOfWork
]:
    async for db in get_async_db_session():
        async with db.begin():
            yield SqlAlchemyPipelineStageUnitOfWork(db)
