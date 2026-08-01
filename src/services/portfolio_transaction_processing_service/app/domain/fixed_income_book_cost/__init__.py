"""Framework-independent fixed-income amortized-cost domain policy."""

from .calculation import (
    AMORTIZED_COST_SCHEDULE_ALGORITHM_ID,
    AMORTIZED_COST_SCHEDULE_ALGORITHM_VERSION,
    AmortizationPeriodInput,
    AmortizationPeriodResult,
    AmortizedCostCalculationError,
    AmortizedCostReconciliationError,
    AmortizedCostScheduleInput,
    AmortizedCostScheduleResult,
    calculate_amortized_cost_schedule,
)
from .policy import (
    AmortizedCostDirection,
    AmortizedCostEligibilityReason,
    AmortizedCostMethod,
    AmortizedCostPolicy,
    AmortizedCostProfileStatus,
    YieldApplicationConvention,
    classify_amortized_cost_direction,
)

__all__ = [
    "AMORTIZED_COST_SCHEDULE_ALGORITHM_ID",
    "AMORTIZED_COST_SCHEDULE_ALGORITHM_VERSION",
    "AmortizedCostDirection",
    "AmortizedCostCalculationError",
    "AmortizedCostEligibilityReason",
    "AmortizedCostMethod",
    "AmortizedCostPolicy",
    "AmortizedCostProfileStatus",
    "AmortizedCostReconciliationError",
    "AmortizedCostScheduleInput",
    "AmortizedCostScheduleResult",
    "AmortizationPeriodInput",
    "AmortizationPeriodResult",
    "YieldApplicationConvention",
    "calculate_amortized_cost_schedule",
    "classify_amortized_cost_direction",
]
