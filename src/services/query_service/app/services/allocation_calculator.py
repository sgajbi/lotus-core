"""Compatibility exports for the shared portfolio allocation policy."""

from portfolio_common.portfolio_allocation import (
    AllocationBucketResult,
    AllocationCalculationResult,
    AllocationInputRow,
    AllocationViewResult,
    calculate_allocation_views,
)

__all__ = [
    "AllocationBucketResult",
    "AllocationCalculationResult",
    "AllocationInputRow",
    "AllocationViewResult",
    "calculate_allocation_views",
]
