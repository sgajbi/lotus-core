"""Concrete transaction processing infrastructure adapters."""

from .average_cost_pool_reconciliation_adapter import (
    SqlAlchemyAverageCostPoolReconciliationAdapter,
)
from .cashflow_processing_adapter import CashflowProcessingCompatibilityAdapter
from .composition import (
    CanonicalBookedTransactionReplayerFactory,
    SqlAlchemyTransactionProcessingUnitOfWorkFactory,
    build_process_transaction_use_case,
    build_reconcile_average_cost_pools_use_case,
    build_replay_booked_transaction_use_case,
)
from .cost_processing_adapter import CostProcessingCompatibilityAdapter
from .pipeline_stage_processing_adapter import PipelineStageProcessingCompatibilityAdapter
from .position_processing_adapter import PositionProcessingCompatibilityAdapter
from .prometheus_cost_basis_observability import (
    PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER,
    PrometheusCostBasisCalculationObserver,
)
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
    "CashflowProcessingCompatibilityAdapter",
    "CostProcessingCompatibilityAdapter",
    "PositionProcessingCompatibilityAdapter",
    "PipelineStageProcessingCompatibilityAdapter",
    "PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER",
    "PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER",
    "PrometheusTransactionProcessingObserver",
    "PrometheusCostBasisCalculationObserver",
    "SqlAlchemyAverageCostPoolReconciliationAdapter",
    "SqlAlchemyBookedTransactionReplayAdapter",
    "SqlAlchemyTransactionIdempotencyAdapter",
    "SqlAlchemyTransactionProcessingUnitOfWork",
    "SqlAlchemyTransactionProcessingUnitOfWorkFactory",
    "TRANSACTION_PROCESSING_SERVICE_NAME",
    "build_process_transaction_use_case",
    "build_reconcile_average_cost_pools_use_case",
    "build_replay_booked_transaction_use_case",
]
