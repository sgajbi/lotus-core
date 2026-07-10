from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import TypeVar

from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from src.services.calculators.cashflow_calculator_service.app.repositories import (
    cashflow_repository,
)
from src.services.calculators.cost_calculator_service.app.cost_calculation_processor import (
    CostCalculationWorkflow,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    CostCalculatorRepository,
)
from src.services.calculators.position_calculator.app.repositories import position_repository

from ..ports import (
    CashflowProcessingPort,
    CostProcessingPort,
    PositionProcessingPort,
    TransactionIdempotencyPort,
)
from .cashflow_processing_adapter import (
    CashflowProcessingCompatibilityAdapter,
    CashflowStagingWorkflow,
)
from .cost_processing_adapter import CostProcessingCompatibilityAdapter
from .position_processing_adapter import PositionProcessingCompatibilityAdapter

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
        correlation_id: str | None,
    ) -> bool:
        return bool(
            await self._repository.claim_event_processing(
                event_id,
                portfolio_id,
                TRANSACTION_PROCESSING_SERVICE_NAME,
                correlation_id,
            )
        )


class SqlAlchemyTransactionProcessingUnitOfWork:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        cost_workflow: CostCalculationWorkflow,
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
            repository=cashflow_repository.CashflowRepository(session),
            idempotency_repository=idempotency_repository,
            outbox_repository=outbox_repository,
        )
        self._position = PositionProcessingCompatibilityAdapter(
            db_session=session,
            repository=position_repository.PositionRepository(session),
            position_state_repository=PositionStateRepository(session),
            outbox_repository=outbox_repository,
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
