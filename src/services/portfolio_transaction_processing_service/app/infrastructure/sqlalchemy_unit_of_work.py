from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import TypeVar

from portfolio_common.idempotency_repository import (
    IdempotencyRepository,
    SemanticEventClaimOutcome,
)
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from ..ports import (
    CashflowProcessingPort,
    CostProcessingPort,
    PipelineStageProcessingPort,
    PositionProcessingPort,
    TransactionIdempotencyOutcome,
    TransactionIdempotencyPort,
)
from .cashflow_processing_adapter import (
    CashflowProcessingCompatibilityAdapter,
    CashflowStagingWorkflow,
)
from .cashflow_repository import SqlAlchemyCashflowRepository
from .cost_processing_adapter import CostProcessingCompatibilityAdapter, CostStagingWorkflow
from .cost_repository import CostCalculatorRepository
from .pipeline_stage_processing_adapter import PipelineStageProcessingAdapter
from .position_processing_adapter import PositionProcessingCompatibilityAdapter
from .position_repository import PositionRepository
from .transaction_stage_repository import SqlAlchemyTransactionStageRepository

TRANSACTION_PROCESSING_SERVICE_NAME = "portfolio-transaction-processing"
_AdapterT = TypeVar("_AdapterT")


class SqlAlchemyTransactionIdempotencyAdapter:
    def __init__(self, repository: IdempotencyRepository) -> None:
        self._repository = repository

    async def claim(
        self,
        *,
        event_id: str,
        portfolio_id: str,
        semantic_key: str,
        payload_fingerprint: str,
        correlation_id: str | None,
    ) -> TransactionIdempotencyOutcome:
        outcome = await self._repository.claim_semantic_event_processing(
            event_id=event_id,
            portfolio_id=portfolio_id,
            service_name=TRANSACTION_PROCESSING_SERVICE_NAME,
            semantic_key=semantic_key,
            payload_fingerprint=payload_fingerprint,
            correlation_id=correlation_id,
        )
        return _map_semantic_claim_outcome(outcome)

    async def claim_repair_delivery(
        self,
        *,
        event_id: str,
        portfolio_id: str,
        correlation_id: str | None,
    ) -> bool:
        return bool(
            await self._repository.claim_event_processing(
                event_id=event_id,
                portfolio_id=portfolio_id,
                service_name=TRANSACTION_PROCESSING_SERVICE_NAME,
                correlation_id=correlation_id,
            )
        )


class SqlAlchemyTransactionProcessingUnitOfWork:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        cost_workflow: CostStagingWorkflow,
        cashflow_workflow: CashflowStagingWorkflow,
    ) -> None:
        self._session_factory = session_factory
        self._cost_workflow = cost_workflow
        self._cashflow_workflow = cashflow_workflow
        self._session: AsyncSession | None = None
        self._transaction: AsyncSessionTransaction | None = None
        self._committed = False
        self._idempotency: TransactionIdempotencyPort | None = None
        self._cost: CostProcessingPort | None = None
        self._cashflow: CashflowProcessingPort | None = None
        self._position: PositionProcessingPort | None = None
        self._pipeline: PipelineStageProcessingPort | None = None

    @property
    def idempotency(self) -> TransactionIdempotencyPort:
        return _required_adapter(self._idempotency, "idempotency")

    @property
    def cost(self) -> CostProcessingPort:
        return _required_adapter(self._cost, "cost")

    @property
    def cashflow(self) -> CashflowProcessingPort:
        return _required_adapter(self._cashflow, "cashflow")

    @property
    def position(self) -> PositionProcessingPort:
        return _required_adapter(self._position, "position")

    @property
    def pipeline(self) -> PipelineStageProcessingPort:
        return _required_adapter(self._pipeline, "pipeline")

    async def __aenter__(self) -> SqlAlchemyTransactionProcessingUnitOfWork:
        if self._session is not None:
            raise RuntimeError("Transaction processing unit of work cannot be reused")
        session = self._session_factory()
        transaction = session.begin()
        self._session = session
        try:
            await transaction.start()
            self._transaction = transaction
            self._build_adapters(session)
        except BaseException:
            if self._transaction is not None:
                await self._transaction.rollback()
            await session.close()
            raise
        return self

    def _build_adapters(self, session: AsyncSession) -> None:
        outbox_repository = OutboxRepository(session)
        idempotency_repository = IdempotencyRepository(session)
        self._idempotency = SqlAlchemyTransactionIdempotencyAdapter(idempotency_repository)
        self._cost = CostProcessingCompatibilityAdapter(
            workflow=self._cost_workflow,
            repository=CostCalculatorRepository(session),
            outbox_repository=outbox_repository,
        )
        self._cashflow = CashflowProcessingCompatibilityAdapter(
            workflow=self._cashflow_workflow,
            db_session=session,
            repository=SqlAlchemyCashflowRepository(session),
            idempotency_repository=idempotency_repository,
            outbox_repository=outbox_repository,
        )
        self._position = PositionProcessingCompatibilityAdapter(
            db_session=session,
            repository=PositionRepository(session),
            position_state_repository=PositionStateRepository(session),
        )
        self._pipeline = PipelineStageProcessingAdapter(
            SqlAlchemyTransactionStageRepository(session),
            outbox_repository,
        )

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        try:
            if not self._committed and self._transaction is not None:
                await self._transaction.rollback()
        finally:
            if self._session is not None:
                await self._session.close()

    async def commit(self) -> None:
        if self._transaction is None:
            raise RuntimeError("Transaction processing unit of work has not been entered")
        if self._committed:
            raise RuntimeError("Transaction processing unit of work was already committed")
        await self._transaction.commit()
        self._committed = True


def _required_adapter(adapter: _AdapterT | None, name: str) -> _AdapterT:
    if adapter is None:
        raise RuntimeError(f"Transaction processing {name} adapter is not initialized")
    return adapter


def _map_semantic_claim_outcome(
    outcome: SemanticEventClaimOutcome,
) -> TransactionIdempotencyOutcome:
    return TransactionIdempotencyOutcome(outcome.value)
