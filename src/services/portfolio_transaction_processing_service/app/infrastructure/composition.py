from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from portfolio_common.db import get_async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cashflow_calculator_service.app.consumers import (
    transaction_consumer as cashflow,
)
from src.services.calculators.cost_calculator_service.app.consumer import (
    CostCalculationWorkflow,
)
from src.services.calculators.cost_calculator_service.app.cost_calculation_processor import (
    CostCalculationWorkflowPort,
)

from ..application import ProcessTransactionUseCase
from .cashflow_processing_adapter import CashflowStagingWorkflow
from .sqlalchemy_unit_of_work import SqlAlchemyTransactionProcessingUnitOfWork


@dataclass(frozen=True, slots=True)
class SqlAlchemyTransactionProcessingUnitOfWorkFactory:
    session_factory: Callable[[], AsyncSession]
    cost_workflow: CostCalculationWorkflowPort
    cashflow_workflow: CashflowStagingWorkflow

    def __call__(self) -> SqlAlchemyTransactionProcessingUnitOfWork:
        return SqlAlchemyTransactionProcessingUnitOfWork(
            session_factory=self.session_factory,
            cost_workflow=self.cost_workflow,
            cashflow_workflow=self.cashflow_workflow,
        )


def build_process_transaction_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> ProcessTransactionUseCase:
    resolved_session_factory = session_factory or get_async_session_factory()
    unit_of_work_factory = SqlAlchemyTransactionProcessingUnitOfWorkFactory(
        session_factory=resolved_session_factory,
        cost_workflow=CostCalculationWorkflow(),
        cashflow_workflow=cashflow.CashflowCalculationWorkflow(),
    )
    return ProcessTransactionUseCase(unit_of_work_factory)
