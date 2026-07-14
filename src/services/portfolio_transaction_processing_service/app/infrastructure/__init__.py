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
from .corporate_action_reconciliation_observability import (
    PROMETHEUS_CORPORATE_ACTION_RECONCILIATION_OBSERVER,
    PrometheusCorporateActionReconciliationObserver,
)
from .cost_basis import (
    PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER,
    PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER,
    PrometheusCostBasisCalculationObserver,
    SqlAlchemyAverageCostPoolReconciliationAdapter,
    cost_basis_processing_lock_key,
)
from .position import PositionHistoryProcessingAdapter
from .prometheus_observability import (
    PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    PrometheusTransactionProcessingObserver,
)
from .sqlalchemy_unit_of_work import SqlAlchemyTransactionProcessingUnitOfWork
from .transaction_replay_adapter import (
    CanonicalTransactionReplayer,
    SqlAlchemyBookedTransactionReplayAdapter,
)

__all__ = [
    "CanonicalBookedTransactionReplayerFactory",
    "CanonicalTransactionReplayer",
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
    "PROMETHEUS_CORPORATE_ACTION_RECONCILIATION_OBSERVER",
    "PrometheusCorporateActionReconciliationObserver",
    "PositionHistoryProcessingAdapter",
    "PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER",
    "PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER",
    "PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER",
    "PrometheusTransactionProcessingObserver",
    "PrometheusCostBasisCalculationObserver",
    "SqlAlchemyAverageCostPoolReconciliationAdapter",
    "SqlAlchemyBookedTransactionReplayAdapter",
    "SqlAlchemyTransactionProcessingUnitOfWork",
    "SqlAlchemyTransactionProcessingUnitOfWorkFactory",
    "UpstreamCashLegUnavailableError",
    "build_process_transaction_use_case",
    "cashflow_calculated_event",
    "cost_basis_processing_lock_key",
    "build_reconcile_average_cost_pools_use_case",
    "build_replay_booked_transaction_use_case",
]
