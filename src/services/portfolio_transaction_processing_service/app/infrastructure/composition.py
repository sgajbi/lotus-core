from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from portfolio_common.db import get_async_session_factory
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.reprocessing_repository import ReprocessingRepository
from sqlalchemy.ext.asyncio import AsyncSession

from ..application import (
    ProcessTransactionUseCase,
    ReconcileAverageCostPoolsUseCase,
    ReplayBookedTransactionUseCase,
)
from ..ports import TransactionProcessingObserver, TransactionProcessingUnitOfWork
from .average_cost_pool_reconciliation_adapter import (
    SqlAlchemyAverageCostPoolReconciliationAdapter,
)
from .cashflow_processing_adapter import CashflowStagingWorkflow
from .cashflow_staging_workflow import CashflowCalculationWorkflow
from .cost_calculation_workflow import CostCalculationWorkflow
from .cost_processing_adapter import CostStagingWorkflow
from .prometheus_cost_basis_observability import (
    PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER,
)
from .prometheus_observability import PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER
from .sqlalchemy_unit_of_work import SqlAlchemyTransactionProcessingUnitOfWork
from .transaction_replay_adapter import (
    CanonicalTransactionReplayer,
    SqlAlchemyBookedTransactionReplayAdapter,
)


@dataclass(frozen=True, slots=True)
class SqlAlchemyTransactionProcessingUnitOfWorkFactory:
    session_factory: Callable[[], AsyncSession]
    cost_workflow: CostStagingWorkflow
    cashflow_workflow: CashflowStagingWorkflow

    def __call__(self) -> TransactionProcessingUnitOfWork:
        return SqlAlchemyTransactionProcessingUnitOfWork(
            session_factory=self.session_factory,
            cost_workflow=self.cost_workflow,
            cashflow_workflow=self.cashflow_workflow,
        )


@dataclass(frozen=True, slots=True)
class CanonicalBookedTransactionReplayerFactory:
    kafka_producer: KafkaProducer

    def __call__(self, session: AsyncSession) -> CanonicalTransactionReplayer:
        return cast(
            CanonicalTransactionReplayer,
            ReprocessingRepository(
                db=session,
                kafka_producer=self.kafka_producer,
            ),
        )


def build_process_transaction_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
    observer: TransactionProcessingObserver | None = None,
) -> ProcessTransactionUseCase:
    resolved_session_factory = session_factory or get_async_session_factory()
    cost_workflow = CostCalculationWorkflow()
    cost_workflow.configure_cost_basis_observer(PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER)
    unit_of_work_factory = SqlAlchemyTransactionProcessingUnitOfWorkFactory(
        session_factory=resolved_session_factory,
        cost_workflow=cost_workflow,
        cashflow_workflow=CashflowCalculationWorkflow(),
    )
    return ProcessTransactionUseCase(
        unit_of_work_factory,
        observer=(observer if observer is not None else PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER),
    )


def build_replay_booked_transaction_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
    kafka_producer: KafkaProducer | None = None,
    observer: TransactionProcessingObserver | None = None,
) -> ReplayBookedTransactionUseCase:
    resolved_session_factory = session_factory or get_async_session_factory()
    resolved_kafka_producer = kafka_producer if kafka_producer is not None else get_kafka_producer()
    replay_adapter = SqlAlchemyBookedTransactionReplayAdapter(
        session_factory=resolved_session_factory,
        replayer_factory=CanonicalBookedTransactionReplayerFactory(
            kafka_producer=resolved_kafka_producer
        ),
    )
    return ReplayBookedTransactionUseCase(
        replay_adapter,
        observer=(observer if observer is not None else PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER),
    )


def build_reconcile_average_cost_pools_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> ReconcileAverageCostPoolsUseCase:
    cost_workflow = CostCalculationWorkflow()
    cost_workflow.configure_cost_basis_observer(PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER)
    reconciliation = SqlAlchemyAverageCostPoolReconciliationAdapter(
        session_factory=session_factory or get_async_session_factory(),
        workflow=cost_workflow,
    )
    return ReconcileAverageCostPoolsUseCase(reconciliation)
