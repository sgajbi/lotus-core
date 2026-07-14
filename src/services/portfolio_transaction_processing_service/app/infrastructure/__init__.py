"""Concrete transaction processing infrastructure adapters."""

from ..application.settlement_processing import UpstreamCashLegUnavailableError
from .cashflow_calculation import (
    TRANSFER_INFLOW_TRANSACTION_TYPES,
    TRANSFER_OUTFLOW_TRANSACTION_TYPES,
    CashflowCalculator,
)
from .cashflow_processing_adapter import CashflowProcessingCompatibilityAdapter
from .cashflow_repository import SqlAlchemyCashflowRepository
from .cashflow_rules_repository import (
    CashflowRuleSetVersion,
    SqlAlchemyCashflowRulesRepository,
)
from .cashflow_staging_workflow import (
    CashflowCalculationWorkflow,
    CashflowProcessingOutcome,
    CashflowStageResult,
    LinkedCashLegError,
    NoCashflowRuleError,
    cashflow_calculated_event_from_stored_cashflow,
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
    StagedCostEffects,
    cost_basis_processing_lock_key,
)
from .cost_calculation_workflow import CostCalculationWorkflow
from .pipeline_stage_processing_adapter import PipelineStageProcessingAdapter
from .position_processing_adapter import PositionHistoryProcessingAdapter
from .prometheus_observability import (
    PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    PrometheusTransactionProcessingObserver,
)
from .sqlalchemy_unit_of_work import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
    SqlAlchemyTransactionIdempotencyAdapter,
    SqlAlchemyTransactionProcessingUnitOfWork,
)
from .transaction_replay_adapter import (
    CanonicalTransactionReplayer,
    SqlAlchemyBookedTransactionReplayAdapter,
)

__all__ = [
    "CanonicalBookedTransactionReplayerFactory",
    "CanonicalTransactionReplayer",
    "CashflowCalculationWorkflow",
    "CashflowCalculator",
    "CashflowProcessingCompatibilityAdapter",
    "CashflowProcessingOutcome",
    "SqlAlchemyCashflowRepository",
    "SqlAlchemyCashflowRulesRepository",
    "CashflowRuleSetVersion",
    "CashflowStageResult",
    "PROMETHEUS_CORPORATE_ACTION_RECONCILIATION_OBSERVER",
    "PrometheusCorporateActionReconciliationObserver",
    "CostCalculationWorkflow",
    "PositionHistoryProcessingAdapter",
    "PipelineStageProcessingAdapter",
    "LinkedCashLegError",
    "NoCashflowRuleError",
    "PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER",
    "PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER",
    "PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER",
    "PrometheusTransactionProcessingObserver",
    "PrometheusCostBasisCalculationObserver",
    "SqlAlchemyAverageCostPoolReconciliationAdapter",
    "SqlAlchemyBookedTransactionReplayAdapter",
    "SqlAlchemyTransactionIdempotencyAdapter",
    "SqlAlchemyTransactionProcessingUnitOfWork",
    "SqlAlchemyTransactionProcessingUnitOfWorkFactory",
    "StagedCostEffects",
    "TRANSACTION_PROCESSING_SERVICE_NAME",
    "TRANSFER_INFLOW_TRANSACTION_TYPES",
    "TRANSFER_OUTFLOW_TRANSACTION_TYPES",
    "UpstreamCashLegUnavailableError",
    "build_process_transaction_use_case",
    "cashflow_calculated_event_from_stored_cashflow",
    "cost_basis_processing_lock_key",
    "build_reconcile_average_cost_pools_use_case",
    "build_replay_booked_transaction_use_case",
]
