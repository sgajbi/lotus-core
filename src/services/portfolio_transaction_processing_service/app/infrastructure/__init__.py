"""Concrete transaction processing infrastructure adapters."""

from ..application.settlement_processing import UpstreamCashLegUnavailableError
from .cashflow import (
    CASHFLOW_PROCESSING_SERVICE_NAME,
    PROMETHEUS_CASHFLOW_CALCULATION_OBSERVER,
    CachedCashflowRule,
    CachedCashflowRuleResolver,
    CashflowRuleCache,
    CashflowRuleCacheState,
    CashflowRuleSetVersion,
    PrometheusCashflowCalculationObserver,
    SqlAlchemyCashflowProcessingState,
    SqlAlchemyCashflowRepository,
    SqlAlchemyCashflowRuleRepository,
    TransactionalCashflowEventStager,
    cashflow_calculated_event,
)
from .composition import (
    CanonicalBookedTransactionReplayerFactory,
    SqlAlchemyTransactionProcessingUnitOfWorkFactory,
    build_process_transaction_use_case,
    build_reconcile_average_cost_pools_use_case,
    build_replay_booked_transaction_use_case,
)
from .cost_basis import (
    PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER,
    PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER,
    PrometheusCostBasisCalculationObserver,
    SqlAlchemyAverageCostPoolReconciliationAdapter,
    cost_basis_processing_lock_key,
)
from .position import PositionHistoryProcessingAdapter
from .sqlalchemy_unit_of_work import SqlAlchemyTransactionProcessingUnitOfWork

__all__ = [
    "CanonicalBookedTransactionReplayerFactory",
    "CASHFLOW_PROCESSING_SERVICE_NAME",
    "CachedCashflowRule",
    "CachedCashflowRuleResolver",
    "CashflowRuleCache",
    "CashflowRuleCacheState",
    "SqlAlchemyCashflowRepository",
    "SqlAlchemyCashflowProcessingState",
    "SqlAlchemyCashflowRuleRepository",
    "TransactionalCashflowEventStager",
    "CashflowRuleSetVersion",
    "PROMETHEUS_CASHFLOW_CALCULATION_OBSERVER",
    "PrometheusCashflowCalculationObserver",
    "PositionHistoryProcessingAdapter",
    "PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER",
    "PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER",
    "PrometheusCostBasisCalculationObserver",
    "SqlAlchemyAverageCostPoolReconciliationAdapter",
    "SqlAlchemyTransactionProcessingUnitOfWork",
    "SqlAlchemyTransactionProcessingUnitOfWorkFactory",
    "UpstreamCashLegUnavailableError",
    "build_process_transaction_use_case",
    "cashflow_calculated_event",
    "cost_basis_processing_lock_key",
    "build_reconcile_average_cost_pools_use_case",
    "build_replay_booked_transaction_use_case",
]
