"""Versioned policy vocabulary for fixed-income amortized book cost."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class AmortizedCostMethod(StrEnum):
    """Supported accounting methods for book-cost evolution."""

    EFFECTIVE_INTEREST = "EFFECTIVE_INTEREST"
    STRAIGHT_LINE = "STRAIGHT_LINE"


class YieldApplicationConvention(StrEnum):
    """Explicit interpretation of the supplied yield or period rate."""

    ANNUAL_EFFECTIVE = "ANNUAL_EFFECTIVE"
    ANNUAL_NOMINAL_SIMPLE = "ANNUAL_NOMINAL_SIMPLE"
    PER_PERIOD_EFFECTIVE = "PER_PERIOD_EFFECTIVE"


class AmortizedCostProfileStatus(StrEnum):
    """Lifecycle of one source-versioned lot amortized-cost profile."""

    ACTIVE = "ACTIVE"
    PARKED = "PARKED"
    INELIGIBLE = "INELIGIBLE"
    TERMINATED = "TERMINATED"
    SUPERSEDED = "SUPERSEDED"


class AmortizedCostEligibilityReason(StrEnum):
    """Stable fail-closed reasons for a non-active profile."""

    ASSIGNMENT_MISSING = "ASSIGNMENT_MISSING"
    ASSIGNMENT_OVERLAPPING = "ASSIGNMENT_OVERLAPPING"
    AUTHORITY_STALE = "AUTHORITY_STALE"
    CLEAN_COST_EVIDENCE_MISSING = "CLEAN_COST_EVIDENCE_MISSING"
    REDEMPTION_VALUE_MISSING = "REDEMPTION_VALUE_MISSING"
    CASHFLOW_SCHEDULE_MISSING = "CASHFLOW_SCHEDULE_MISSING"
    EFFECTIVE_YIELD_MISSING = "EFFECTIVE_YIELD_MISSING"
    YIELD_CONVENTION_MISSING = "YIELD_CONVENTION_MISSING"
    POLICY_UNSUPPORTED = "POLICY_UNSUPPORTED"
    RESIDUAL_OUTSIDE_TOLERANCE = "RESIDUAL_OUTSIDE_TOLERANCE"


class AmortizedCostDirection(StrEnum):
    """Economic direction from opening clean book cost to redemption value."""

    PREMIUM_AMORTIZATION = "PREMIUM_AMORTIZATION"
    DISCOUNT_ACCRETION = "DISCOUNT_ACCRETION"
    AT_PAR = "AT_PAR"


@dataclass(frozen=True, slots=True)
class AmortizedCostPolicy:
    """One versioned accounting policy independent of source and persistence models."""

    policy_id: str
    policy_version: int
    method: AmortizedCostMethod
    yield_application_convention: YieldApplicationConvention | None
    include_fees_in_initial_basis: bool
    residual_tolerance_local: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str):
            raise TypeError("policy_id must be a string")
        normalized_policy_id = self.policy_id.strip()
        if not normalized_policy_id:
            raise ValueError("policy_id must be nonblank")
        object.__setattr__(self, "policy_id", normalized_policy_id)
        if not isinstance(self.policy_version, int) or isinstance(self.policy_version, bool):
            raise TypeError("policy_version must be an integer")
        if self.policy_version < 1:
            raise ValueError("policy_version must be positive")
        if not isinstance(self.method, AmortizedCostMethod):
            raise TypeError("method must be an AmortizedCostMethod")
        if self.yield_application_convention is not None and not isinstance(
            self.yield_application_convention,
            YieldApplicationConvention,
        ):
            raise TypeError(
                "yield_application_convention must be a YieldApplicationConvention or None"
            )
        if not isinstance(self.include_fees_in_initial_basis, bool):
            raise TypeError("include_fees_in_initial_basis must be a boolean")
        if self.method is AmortizedCostMethod.EFFECTIVE_INTEREST:
            if self.yield_application_convention is None:
                raise ValueError("effective-interest policy requires a yield convention")
        elif self.yield_application_convention is not None:
            raise ValueError("straight-line policy must not declare a yield convention")
        if not isinstance(self.residual_tolerance_local, Decimal):
            raise TypeError("residual_tolerance_local must be a Decimal")
        if not self.residual_tolerance_local.is_finite():
            raise ValueError("residual_tolerance_local must be finite")
        if self.residual_tolerance_local < 0:
            raise ValueError("residual_tolerance_local must be nonnegative")


def classify_amortized_cost_direction(
    *,
    opening_amortized_cost_local: Decimal,
    redemption_value_local: Decimal,
) -> AmortizedCostDirection:
    """Classify premium, discount, or par without product-name inference."""

    _require_nonnegative_finite(opening_amortized_cost_local, "opening_amortized_cost_local")
    _require_nonnegative_finite(redemption_value_local, "redemption_value_local")
    if opening_amortized_cost_local > redemption_value_local:
        return AmortizedCostDirection.PREMIUM_AMORTIZATION
    if opening_amortized_cost_local < redemption_value_local:
        return AmortizedCostDirection.DISCOUNT_ACCRETION
    return AmortizedCostDirection.AT_PAR


def _require_nonnegative_finite(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative")
