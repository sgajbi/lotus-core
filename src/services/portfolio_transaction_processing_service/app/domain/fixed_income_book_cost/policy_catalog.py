"""Versioned amortized-cost methodologies supported by the Core runtime."""

from __future__ import annotations

from decimal import Decimal

from .policy import (
    AmortizedCostMethod,
    AmortizedCostPolicy,
    YieldApplicationConvention,
)

IFRS9_EIR_LOCAL_POLICY_ID = "IFRS9_EIR_LOCAL"
STRAIGHT_LINE_LOCAL_POLICY_ID = "STRAIGHT_LINE_LOCAL"


def governed_amortized_cost_policy_catalog() -> tuple[AmortizedCostPolicy, ...]:
    """Return immutable, code-reviewed calculation semantics for source assignment.

    Policy identifiers are stable contracts. Existing versions must never be edited in place;
    methodology changes require a new version so persisted assignments and replay remain exact.
    """

    return (
        AmortizedCostPolicy(
            policy_id=IFRS9_EIR_LOCAL_POLICY_ID,
            policy_version=1,
            method=AmortizedCostMethod.EFFECTIVE_YIELD,
            yield_application_convention=YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE,
            include_fees_in_amortized_cost=True,
            residual_tolerance_local=Decimal("0.0000000001"),
        ),
        AmortizedCostPolicy(
            policy_id=STRAIGHT_LINE_LOCAL_POLICY_ID,
            policy_version=1,
            method=AmortizedCostMethod.STRAIGHT_LINE,
            yield_application_convention=None,
            include_fees_in_amortized_cost=True,
            residual_tolerance_local=Decimal("0.0000000001"),
        ),
    )
