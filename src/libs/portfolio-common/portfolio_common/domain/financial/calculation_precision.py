"""Explicit precision policy for values derived by financial calculations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from typing import Callable, Iterator

from .precision import (
    DecimalPrecisionError,
    DecimalPrecisionPolicy,
    DecimalPrecisionViolation,
)

DecimalBinaryOperation = Callable[[Decimal, Decimal], Decimal]


@dataclass(frozen=True, slots=True)
class CalculatedDecimalPolicy:
    """Normalize derived values with deterministic high-precision arithmetic."""

    name: str
    version: str
    precision: int
    scale: int
    working_precision: int = 64
    rounding: str = ROUND_HALF_EVEN
    _persistence_policy: DecimalPrecisionPolicy = field(init=False, repr=False)
    _quantum: Decimal = field(init=False, repr=False)

    def __post_init__(self) -> None:
        persistence_policy = DecimalPrecisionPolicy(
            name=f"{self.name}@{self.version}",
            precision=self.precision,
            scale=self.scale,
        )
        if self.working_precision < self.precision * 2:
            raise ValueError(
                "calculation working precision must be at least twice storage precision"
            )
        object.__setattr__(self, "_persistence_policy", persistence_policy)
        object.__setattr__(self, "_quantum", Decimal(1).scaleb(-self.scale))

    @property
    def policy_id(self) -> str:
        return self._persistence_policy.name

    @contextmanager
    def arithmetic_context(self) -> Iterator[None]:
        """Run intermediate arithmetic without inheriting ambient Decimal precision."""

        with localcontext() as context:
            context.prec = self.working_precision
            yield

    def normalize(self, value: Decimal, *, field_name: str) -> Decimal:
        """Round a finite derived value once, then prove exact persistence."""

        if not isinstance(value, Decimal) or not value.is_finite():
            raise DecimalPrecisionError(
                field_name=field_name,
                violation=DecimalPrecisionViolation.NON_FINITE,
                policy_name=self.policy_id,
            )
        try:
            return self._persistence_policy.require_exact(
                value,
                field_name=field_name,
            )
        except DecimalPrecisionError as exc:
            if exc.violation is not DecimalPrecisionViolation.EXCESS_SCALE:
                raise
        try:
            with localcontext() as context:
                context.prec = self.working_precision
                normalized = value.quantize(self._quantum, rounding=self.rounding)
        except InvalidOperation as exc:
            raise DecimalPrecisionError(
                field_name=field_name,
                violation=DecimalPrecisionViolation.MAGNITUDE_OVERFLOW,
                policy_name=self.policy_id,
            ) from exc
        return self._persistence_policy.require_exact(
            normalized,
            field_name=field_name,
        )

    def add(self, left: Decimal, right: Decimal, *, field_name: str) -> Decimal:
        return self._calculate(left, right, field_name=field_name, operation=lambda a, b: a + b)

    def subtract(self, left: Decimal, right: Decimal, *, field_name: str) -> Decimal:
        return self._calculate(left, right, field_name=field_name, operation=lambda a, b: a - b)

    def multiply(self, left: Decimal, right: Decimal, *, field_name: str) -> Decimal:
        return self._calculate(left, right, field_name=field_name, operation=lambda a, b: a * b)

    def divide(self, dividend: Decimal, divisor: Decimal, *, field_name: str) -> Decimal:
        if divisor.is_zero():
            raise ZeroDivisionError(f"{field_name} divisor must not be zero")
        return self._calculate(
            dividend,
            divisor,
            field_name=field_name,
            operation=lambda a, b: a / b,
        )

    def _calculate(
        self,
        left: Decimal,
        right: Decimal,
        *,
        field_name: str,
        operation: DecimalBinaryOperation,
    ) -> Decimal:
        if not left.is_finite() or not right.is_finite():
            raise DecimalPrecisionError(
                field_name=field_name,
                violation=DecimalPrecisionViolation.NON_FINITE,
                policy_name=self.policy_id,
            )
        with self.arithmetic_context():
            result = operation(left, right)
        return self.normalize(result, field_name=field_name)
