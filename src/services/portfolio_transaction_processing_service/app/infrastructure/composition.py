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
from ..application.cost_basis_processing import (
    AverageCostPoolRebuildPlanner,
    PreparedCostProcessingUseCase,
)
from ..ports import TransactionProcessingObserver, TransactionProcessingUnitOfWork
from .cashflow import CashflowRuleCache
from .cost_basis import (
    PROMETHEUS_CORPORATE_ACTION_RECONCILIATION_OBSERVER,
    PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER,
    PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER,
    SqlAlchemyAverageCostPoolReconciliationAdapter,
)
from .transaction_processing import (
    PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    SqlAlchemyTransactionProcessingUnitOfWork,
)
from .transaction_replay import (
    CanonicalTransactionReplayer,
    SqlAlchemyBookedTransactionReplayAdapter,
)


@dataclass(frozen=True, slots=True)
class SqlAlchemyTransactionProcessingUnitOfWorkFactory:
    session_factory: Callable[[], AsyncSession]
    cost_processor: PreparedCostProcessingUseCase
    cashflow_rule_cache: CashflowRuleCache

    def __call__(self) -> TransactionProcessingUnitOfWork:
        return SqlAlchemyTransactionProcessingUnitOfWork(
            session_factory=self.session_factory,
            cost_processor=self.cost_processor,
            cashflow_rule_cache=self.cashflow_rule_cache,
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
    cost_processor = PreparedCostProcessingUseCase(
        calculation_observer=PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER,
        persistence_observer=PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER,
        reconciliation_observer=PROMETHEUS_CORPORATE_ACTION_RECONCILIATION_OBSERVER,
    )
    unit_of_work_factory = SqlAlchemyTransactionProcessingUnitOfWorkFactory(
        session_factory=resolved_session_factory,
        cost_processor=cost_processor,
        cashflow_rule_cache=CashflowRuleCache(),
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
    reconciliation = SqlAlchemyAverageCostPoolReconciliationAdapter(
        session_factory=session_factory or get_async_session_factory(),
        rebuild_planner=AverageCostPoolRebuildPlanner(
            observer=PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER
        ),
    )
    return ReconcileAverageCostPoolsUseCase(reconciliation)
