"""Compose transaction-processing application use cases from concrete adapters."""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from portfolio_common.db import get_async_session_factory
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.reprocessing_repository import ReprocessingRepository
from sqlalchemy.ext.asyncio import AsyncSession

from ..application import (
    AuditLotPositionParityUseCase,
    ProcessNextCorporateActionReleaseUseCase,
    ProcessTransactionUseCase,
    ReconcileAverageCostPoolsUseCase,
    ReplayBookedTransactionUseCase,
    RouteCorporateActionChildArrivalUseCase,
)
from ..application.corporate_action_manifest_ingestion import (
    HandleCorporateActionManifestEventUseCase,
)
from ..application.cost_basis_processing import (
    AverageCostPoolRebuildPlanner,
    PreparedCostProcessingUseCase,
)
from ..application.fixed_income_book_cost import (
    HandleFixedIncomeBookCostAuthorityEventUseCase,
)
from ..domain.fixed_income_book_cost import (
    AmortizedCostPolicyRegistry,
    governed_amortized_cost_policy_catalog,
)
from ..infrastructure.cashflow import CashflowRuleCache
from ..infrastructure.corporate_action_event_graph import (
    SqlAlchemyCorporateActionEventGraphUnitOfWork,
)
from ..infrastructure.corporate_action_release_observability import (
    PROMETHEUS_CORPORATE_ACTION_RELEASE_OBSERVER,
)
from ..infrastructure.cost_basis import (
    PROMETHEUS_CORPORATE_ACTION_RECONCILIATION_OBSERVER,
    PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER,
    PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER,
    SqlAlchemyAverageCostPoolReconciliationAdapter,
    SqlAlchemyLotPositionParityAdapter,
)
from ..infrastructure.fixed_income_book_cost import (
    SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork,
)
from ..infrastructure.transaction_processing import (
    PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    SqlAlchemyTransactionProcessingUnitOfWork,
)
from ..infrastructure.transaction_replay import (
    CanonicalTransactionReplayer,
    SqlAlchemyBookedTransactionReplayAdapter,
)
from ..ports import TransactionProcessingObserver, TransactionProcessingUnitOfWork


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
class SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWorkFactory:
    session_factory: Callable[[], AsyncSession]

    def __call__(self) -> SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork:
        return SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork(self.session_factory)


@dataclass(frozen=True, slots=True)
class SqlAlchemyCorporateActionEventGraphUnitOfWorkFactory:
    session_factory: Callable[[], AsyncSession]

    def __call__(self) -> SqlAlchemyCorporateActionEventGraphUnitOfWork:
        return SqlAlchemyCorporateActionEventGraphUnitOfWork(self.session_factory)


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


def build_audit_lot_position_parity_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> AuditLotPositionParityUseCase:
    return AuditLotPositionParityUseCase(
        SqlAlchemyLotPositionParityAdapter(
            session_factory=session_factory or get_async_session_factory()
        )
    )


def build_fixed_income_book_cost_authority_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
    policies: AmortizedCostPolicyRegistry | None = None,
    correction_replay_enabled: bool = False,
) -> HandleFixedIncomeBookCostAuthorityEventUseCase:
    """Compose authority handling with replay fail-closed until its consumer is certified."""

    resolved_policies = policies or AmortizedCostPolicyRegistry(
        governed_amortized_cost_policy_catalog()
    )
    return HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWorkFactory(
            session_factory=session_factory or get_async_session_factory()
        ),
        policies=resolved_policies,
        correction_replay_enabled=correction_replay_enabled,
    )


def build_corporate_action_manifest_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> HandleCorporateActionManifestEventUseCase:
    """Compose source-manifest registration over the lightweight graph UoW."""

    return HandleCorporateActionManifestEventUseCase(
        SqlAlchemyCorporateActionEventGraphUnitOfWorkFactory(
            session_factory=session_factory or get_async_session_factory()
        )
    )


def build_corporate_action_child_arrival_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> RouteCorporateActionChildArrivalUseCase:
    """Compose atomic child parking and READY release materialization."""

    return RouteCorporateActionChildArrivalUseCase(
        SqlAlchemyCorporateActionEventGraphUnitOfWorkFactory(
            session_factory=session_factory or get_async_session_factory()
        )
    )


def build_corporate_action_release_worker_use_case(
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
    process_transaction: ProcessTransactionUseCase | None = None,
    lease_owner: str | None = None,
) -> ProcessNextCorporateActionReleaseUseCase:
    """Compose the fenced worker over the same mature PostgreSQL boundary."""

    resolved_session_factory = session_factory or get_async_session_factory()
    return ProcessNextCorporateActionReleaseUseCase(
        unit_of_work_factory=SqlAlchemyCorporateActionEventGraphUnitOfWorkFactory(
            session_factory=resolved_session_factory
        ),
        process_transaction=(
            process_transaction
            if process_transaction is not None
            else build_process_transaction_use_case(session_factory=resolved_session_factory)
        ),
        lease_owner=lease_owner or f"{socket.gethostname()}:{os.getpid()}",
        observer=PROMETHEUS_CORPORATE_ACTION_RELEASE_OBSERVER,
    )
