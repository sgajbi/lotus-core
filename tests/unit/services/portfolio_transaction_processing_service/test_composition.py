from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cashflow_calculator_service.app.consumers import (
    transaction_consumer as cashflow,
)
from src.services.calculators.cost_calculator_service.app.consumer import (
    CostCalculationWorkflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    SqlAlchemyTransactionProcessingUnitOfWork,
    SqlAlchemyTransactionProcessingUnitOfWorkFactory,
    build_process_transaction_use_case,
)


def test_composition_reuses_plain_workflows_and_creates_unit_of_work_per_message() -> None:
    session_factory = MagicMock(spec=lambda: AsyncSession())
    cost_workflow = CostCalculationWorkflow()
    cashflow_workflow = cashflow.CashflowCalculationWorkflow()
    factory = SqlAlchemyTransactionProcessingUnitOfWorkFactory(
        session_factory=session_factory,
        cost_workflow=cost_workflow,
        cashflow_workflow=cashflow_workflow,
    )

    first = factory()
    second = factory()

    assert isinstance(first, SqlAlchemyTransactionProcessingUnitOfWork)
    assert isinstance(second, SqlAlchemyTransactionProcessingUnitOfWork)
    assert first is not second
    assert first._cost_workflow is second._cost_workflow is cost_workflow
    assert first._cashflow_workflow is second._cashflow_workflow is cashflow_workflow
    assert not hasattr(cost_workflow, "_consumer_config")
    assert not hasattr(cashflow_workflow, "_consumer_config")


def test_use_case_builder_accepts_repository_standard_session_factory() -> None:
    session_factory = MagicMock(spec=lambda: AsyncSession())

    use_case = build_process_transaction_use_case(session_factory=session_factory)

    unit_of_work = use_case._unit_of_work_factory()
    assert isinstance(unit_of_work, SqlAlchemyTransactionProcessingUnitOfWork)
    assert unit_of_work._session_factory is session_factory
