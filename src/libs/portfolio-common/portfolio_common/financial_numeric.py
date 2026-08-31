"""SQLAlchemy numeric type that rejects lossy persistence."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Numeric
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator

from .domain.financial.precision import (
    BOUNDED_18_4_EXACT,
    BOUNDED_18_10_EXACT,
    EXACT_UNBOUNDED,
    DecimalPrecisionPolicy,
)

_SUPPORTED_BOUNDED_POLICIES = {
    (18, 10): BOUNDED_18_10_EXACT,
    (18, 4): BOUNDED_18_4_EXACT,
}
_POSTGRESQL_SPECIAL_NUMERIC_VALUES = ("NaN", "Infinity", "-Infinity")


def finite_numeric_check_constraint(name: str, *column_names: str) -> CheckConstraint:
    """Build one explicit PostgreSQL finite-value check for numeric columns."""

    if not column_names:
        raise ValueError("at least one numeric column is required")
    if any(not column_name.isidentifier() for column_name in column_names):
        raise ValueError("numeric column names must be identifiers")
    special_values = ", ".join(f"'{value}'" for value in _POSTGRESQL_SPECIAL_NUMERIC_VALUES)
    condition = " AND ".join(
        f"CAST({column_name} AS TEXT) NOT IN ({special_values})" for column_name in column_names
    )
    return CheckConstraint(condition, name=name)


class ExactNumeric(TypeDecorator[Decimal]):
    """Preserve SQL ``NUMERIC`` DDL while rejecting implicit rounding on binds."""

    impl = Numeric
    cache_ok = True

    def __init__(
        self,
        precision: int | None = None,
        scale: int | None = None,
        *,
        asdecimal: bool = True,
    ) -> None:
        if asdecimal is not True:
            raise ValueError("ExactNumeric requires Decimal result semantics")
        self.precision = precision
        self.scale = scale
        super().__init__(precision=precision, scale=scale, asdecimal=asdecimal)

    def _precision_policy(self) -> DecimalPrecisionPolicy:
        if self.precision is None and self.scale is None:
            return EXACT_UNBOUNDED
        try:
            return _SUPPORTED_BOUNDED_POLICIES[(self.precision, self.scale)]
        except KeyError as exc:
            raise ValueError(
                "ExactNumeric requires a governed precision/scale policy; "
                f"received ({self.precision}, {self.scale})"
            ) from exc

    def process_bind_param(self, value: Any, _dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if _dialect.name not in {"default", "postgresql"}:
            raise RuntimeError("ExactNumeric persistence requires PostgreSQL")
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        return self._precision_policy().require_exact(
            decimal_value,
            field_name="database numeric value",
        )
