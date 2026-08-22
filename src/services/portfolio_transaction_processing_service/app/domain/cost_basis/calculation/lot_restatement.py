"""Exact quantity-restatement policy for cost-basis lot books."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_PERSISTENCE_PRECISION_V1,
)

LOT_QUANTITY_SCALE = 10
_LOT_QUANTITY_SCALE_FACTOR = 10**LOT_QUANTITY_SCALE


class LotRestatementError(ValueError):
    """Raised when a lot restatement cannot be represented without rounding."""


@dataclass(frozen=True, slots=True)
class LotRestatement:
    """Apply one exact before/after book ratio to every quantity in a lot book.

    The transaction carries a quantity delta, while the lot book needs a common
    multiplicative ratio.  Keeping the ratio as its exact before/after Decimal
    authorities avoids storing a rounded repeating factor such as ``4 / 3``.
    """

    quantity_before: Decimal
    quantity_after: Decimal

    def __post_init__(self) -> None:
        _require_positive_persistable_quantity(self.quantity_before, "quantity_before")
        _require_positive_persistable_quantity(self.quantity_after, "quantity_after")
        if self.quantity_before == self.quantity_after:
            raise LotRestatementError("lot restatement must change quantity")

    @classmethod
    def from_signed_delta(
        cls,
        *,
        quantity_before: Decimal,
        signed_quantity_delta: Decimal,
    ) -> LotRestatement:
        """Build a restatement from the current book quantity and signed event delta."""

        _require_finite_decimal(signed_quantity_delta, "signed_quantity_delta")
        quantity_after = quantity_before + signed_quantity_delta
        return cls(quantity_before=quantity_before, quantity_after=quantity_after)

    def apply(self, quantity: Decimal, *, field_name: str) -> Decimal:
        """Scale one quantity and reject values requiring storage rounding."""

        _require_non_negative_persistable_quantity(quantity, field_name)
        scaled = Fraction(quantity) * Fraction(self.quantity_after) / Fraction(
            self.quantity_before
        )
        storage_units = scaled * _LOT_QUANTITY_SCALE_FACTOR
        if storage_units.denominator != 1:
            raise LotRestatementError(
                f"{field_name} cannot be restated exactly at {LOT_QUANTITY_SCALE} decimal places"
            )
        result = Decimal(storage_units.numerator).scaleb(-LOT_QUANTITY_SCALE)
        return TRANSACTION_PERSISTENCE_PRECISION_V1.require_exact(
            result,
            field_name=field_name,
        )

    def lineage_payload(self) -> dict[str, Decimal]:
        """Return the exact ratio authority for calculation lineage."""

        return {
            "quantity_before": self.quantity_before,
            "quantity_after": self.quantity_after,
            "factor_numerator": self.quantity_after,
            "factor_denominator": self.quantity_before,
        }


def _require_finite_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise LotRestatementError(f"{field_name} must be finite")


def _require_non_negative_persistable_quantity(value: object, field_name: str) -> None:
    _require_finite_decimal(value, field_name)
    if value < Decimal(0):
        raise LotRestatementError(f"{field_name} must be non-negative")
    TRANSACTION_PERSISTENCE_PRECISION_V1.require_exact(value, field_name=field_name)


def _require_positive_persistable_quantity(value: object, field_name: str) -> None:
    _require_non_negative_persistable_quantity(value, field_name)
    if value == Decimal(0):
        raise LotRestatementError(f"{field_name} must be positive")
