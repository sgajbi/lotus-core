"""Exact Decimal persistence-boundary policies shared across Core domains."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class DecimalPrecisionViolation(StrEnum):
    NON_FINITE = "non_finite"
    EXCESS_SCALE = "excess_scale"
    MAGNITUDE_OVERFLOW = "magnitude_overflow"


class DecimalPrecisionError(ValueError):
    """Describe a product-safe precision rejection without retaining the value."""

    def __init__(
        self,
        *,
        field_name: str,
        violation: DecimalPrecisionViolation,
        policy_name: str,
    ) -> None:
        self.field_name = field_name
        self.violation = violation
        self.policy_name = policy_name
        super().__init__(
            f"{field_name} violates Decimal precision policy {policy_name}: {violation.value}"
        )


@dataclass(frozen=True, slots=True)
class DecimalPrecisionPolicy:
    """Validate exact representability without applying implicit rounding."""

    name: str
    precision: int | None
    scale: int | None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Decimal precision policy name is required")
        if self.precision is None or self.scale is None:
            if self.precision is not None or self.scale is not None:
                raise ValueError("unbounded Decimal policy requires null precision and scale")
            return
        if self.precision <= 0:
            raise ValueError("Decimal precision must be greater than zero")
        if self.scale < 0 or self.scale > self.precision:
            raise ValueError("Decimal scale must satisfy 0 <= scale <= precision")

    @property
    def is_unbounded(self) -> bool:
        return self.precision is None

    def require_exact(self, value: Decimal, *, field_name: str) -> Decimal:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise DecimalPrecisionError(
                field_name=field_name,
                violation=DecimalPrecisionViolation.NON_FINITE,
                policy_name=self.name,
            )
        if self.is_unbounded or value.is_zero():
            return value

        precision = self.precision
        scale = self.scale
        if precision is None or scale is None:
            raise RuntimeError("bounded Decimal policy is missing precision or scale")
        digits = list(value.as_tuple().digits)
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int):
            raise DecimalPrecisionError(
                field_name=field_name,
                violation=DecimalPrecisionViolation.NON_FINITE,
                policy_name=self.name,
            )
        while digits and digits[-1] == 0 and exponent < 0:
            digits.pop()
            exponent += 1
        significant_digit_count = len(digits)
        fractional_digit_count = max(-exponent, 0)
        if fractional_digit_count > scale:
            raise DecimalPrecisionError(
                field_name=field_name,
                violation=DecimalPrecisionViolation.EXCESS_SCALE,
                policy_name=self.name,
            )
        integer_digit_count = max(significant_digit_count + exponent, 0)
        if integer_digit_count > precision - scale:
            raise DecimalPrecisionError(
                field_name=field_name,
                violation=DecimalPrecisionViolation.MAGNITUDE_OVERFLOW,
                policy_name=self.name,
            )
        return value


EXACT_UNBOUNDED = DecimalPrecisionPolicy(
    name="exact-unbounded",
    precision=None,
    scale=None,
)
BOUNDED_18_10_EXACT = DecimalPrecisionPolicy(
    name="bounded-18-10-exact",
    precision=18,
    scale=10,
)
BOUNDED_18_4_EXACT = DecimalPrecisionPolicy(
    name="bounded-18-4-exact",
    precision=18,
    scale=4,
)
