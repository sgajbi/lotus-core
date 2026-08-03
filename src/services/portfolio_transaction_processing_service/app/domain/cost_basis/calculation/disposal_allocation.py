"""Immutable source-lot allocation evidence produced during cost-basis disposal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)


@dataclass(frozen=True, slots=True)
class SourceLotDisposalAllocation:
    """One deterministic source-lot contribution to a disposal result."""

    source_lot_id: str
    source_transaction_id: str
    source_acquisition_date: date
    allocation_ordinal: int
    consumed_quantity: Decimal
    consumed_cost_local: Decimal
    consumed_cost_base: Decimal

    def __post_init__(self) -> None:
        for field_name in ("source_lot_id", "source_transaction_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        if type(self.source_acquisition_date) is not date:
            raise TypeError("source_acquisition_date must be a date")
        if not isinstance(self.allocation_ordinal, int) or isinstance(
            self.allocation_ordinal, bool
        ):
            raise TypeError("allocation_ordinal must be an integer")
        if self.allocation_ordinal < 1:
            raise ValueError("allocation_ordinal must be positive")
        _require_decimal(self.consumed_quantity, "consumed_quantity", positive=True)
        _require_decimal(self.consumed_cost_local, "consumed_cost_local")
        _require_decimal(self.consumed_cost_base, "consumed_cost_base")


@dataclass(frozen=True, slots=True)
class LotDisposalResult:
    """Aggregate cost result plus exact source-lot allocation evidence."""

    cost_base: Decimal
    cost_local: Decimal
    consumed_quantity: Decimal
    allocations: tuple[SourceLotDisposalAllocation, ...]
    error_reason: str | None = None

    def __post_init__(self) -> None:
        _require_decimal(self.cost_base, "cost_base")
        _require_decimal(self.cost_local, "cost_local")
        _require_decimal(self.consumed_quantity, "consumed_quantity")
        if not isinstance(self.allocations, tuple) or not all(
            isinstance(allocation, SourceLotDisposalAllocation) for allocation in self.allocations
        ):
            raise TypeError("allocations must be a tuple of SourceLotDisposalAllocation")
        ordinals = tuple(allocation.allocation_ordinal for allocation in self.allocations)
        if ordinals != tuple(range(1, len(self.allocations) + 1)):
            raise ValueError("allocation ordinals must be contiguous from one")
        source_lot_ids = tuple(allocation.source_lot_id for allocation in self.allocations)
        if len(set(source_lot_ids)) != len(source_lot_ids):
            raise ValueError("a source lot can appear only once in one disposal result")
        if self.error_reason is not None:
            if not isinstance(self.error_reason, str):
                raise TypeError("error_reason must be a string or None")
            normalized_error = self.error_reason.strip()
            if not normalized_error:
                raise ValueError("error_reason must be nonblank when supplied")
            object.__setattr__(self, "error_reason", normalized_error)
            if any((self.cost_base, self.cost_local, self.consumed_quantity)) or self.allocations:
                raise ValueError("failed disposal results cannot carry economics or allocations")
            return
        if self.consumed_quantity == Decimal(0):
            if any((self.cost_base, self.cost_local)) or self.allocations:
                raise ValueError("zero-quantity disposal results must be empty")
            return
        if not self.allocations:
            raise ValueError("successful disposal must carry source-lot allocations")
        _require_allocation_conservation(self)

    @classmethod
    def failed(cls, reason: str) -> LotDisposalResult:
        """Build one zero-economics failed result."""

        return cls(
            cost_base=Decimal(0),
            cost_local=Decimal(0),
            consumed_quantity=Decimal(0),
            allocations=(),
            error_reason=reason,
        )

    @classmethod
    def empty(cls) -> LotDisposalResult:
        """Build the backward-compatible zero-quantity no-op result."""

        return cls(
            cost_base=Decimal(0),
            cost_local=Decimal(0),
            consumed_quantity=Decimal(0),
            allocations=(),
        )

    def legacy_tuple(self) -> tuple[Decimal, Decimal, Decimal, str | None]:
        """Project the existing aggregate strategy contract during staged adoption."""

        return self.cost_base, self.cost_local, self.consumed_quantity, self.error_reason


def _require_allocation_conservation(result: LotDisposalResult) -> None:
    policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1
    quantity = Decimal(0)
    cost_local = Decimal(0)
    cost_base = Decimal(0)
    for allocation in result.allocations:
        quantity = policy.add(
            quantity,
            allocation.consumed_quantity,
            field_name="allocated_disposal_quantity",
        )
        cost_local = policy.add(
            cost_local,
            allocation.consumed_cost_local,
            field_name="allocated_disposal_cost_local",
        )
        cost_base = policy.add(
            cost_base,
            allocation.consumed_cost_base,
            field_name="allocated_disposal_cost_base",
        )
    if quantity != result.consumed_quantity:
        raise ValueError("source-lot allocation quantity does not reconcile to disposal aggregate")
    if cost_local != result.cost_local:
        raise ValueError("source-lot local cost does not reconcile to disposal aggregate")
    if cost_base != result.cost_base:
        raise ValueError("source-lot base cost does not reconcile to disposal aggregate")


def _require_decimal(value: object, field_name: str, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < Decimal(0) or (positive and value == Decimal(0)):
        requirement = "positive" if positive else "non-negative"
        raise ValueError(f"{field_name} must be {requirement}")
