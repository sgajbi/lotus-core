"""Immutable source-lot evidence for basis-only corporate-action transfers."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    BASIS_TRANSFER_LINEAGE_ALGORITHM_ID,
    BASIS_TRANSFER_LINEAGE_ALGORITHM_VERSION,
    basis_transfer_lineage_input_payload,
    basis_transfer_lineage_output_payload,
)
from portfolio_common.domain.decimal_amount import required_decimal
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    return normalized


def _nonnegative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    normalized = cast(Decimal, required_decimal(value, field_name=field_name))
    if not normalized.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if normalized < Decimal(0):
        raise ValueError(f"{field_name} must be nonnegative")
    return normalized


def _sum_amounts(values: tuple[Decimal, ...], *, field_name: str) -> Decimal:
    total = Decimal(0)
    for value in values:
        total = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            total,
            value,
            field_name=field_name,
        )
    return total


@dataclass(frozen=True, slots=True)
class SourceLotBasisTransferAllocation:
    """One source lot's basis contribution to a zero-quantity target leg."""

    allocation_ordinal: int
    source_lot_id: str
    source_transaction_id: str
    source_acquisition_date: date
    retained_quantity: Decimal
    source_cost_local_before: Decimal
    source_cost_base_before: Decimal
    transferred_cost_local: Decimal
    transferred_cost_base: Decimal
    retained_cost_local: Decimal
    retained_cost_base: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.allocation_ordinal, int) or self.allocation_ordinal < 1:
            raise ValueError("allocation_ordinal must be a positive integer")
        object.__setattr__(
            self,
            "source_lot_id",
            _required_text(self.source_lot_id, field_name="source_lot_id"),
        )
        object.__setattr__(
            self,
            "source_transaction_id",
            _required_text(self.source_transaction_id, field_name="source_transaction_id"),
        )
        if not isinstance(self.source_acquisition_date, date):
            raise TypeError("source_acquisition_date must be a date")
        for field_name in (
            "retained_quantity",
            "source_cost_local_before",
            "source_cost_base_before",
            "transferred_cost_local",
            "transferred_cost_base",
            "retained_cost_local",
            "retained_cost_base",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative_decimal(getattr(self, field_name), field_name=field_name),
            )
        if self.retained_quantity <= Decimal(0):
            raise ValueError("retained_quantity must be positive")
        if self.transferred_cost_local.is_zero() and self.transferred_cost_base.is_zero():
            raise ValueError("basis-transfer allocations require a positive basis movement")
        if self.transferred_cost_local + self.retained_cost_local != self.source_cost_local_before:
            raise ValueError("source local basis must equal transferred plus retained basis")
        if self.transferred_cost_base + self.retained_cost_base != self.source_cost_base_before:
            raise ValueError("source base basis must equal transferred plus retained basis")


@dataclass(frozen=True, slots=True)
class LotBasisTransferResult:
    """Conserved per-source evidence for one successful basis-only transfer."""

    transferred_cost_local: Decimal
    transferred_cost_base: Decimal
    allocations: tuple[SourceLotBasisTransferAllocation, ...]
    error_reason: str | None = None
    calculation_lineage: CalculationLineage | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        for field_name in ("transferred_cost_local", "transferred_cost_base"):
            object.__setattr__(
                self,
                field_name,
                _nonnegative_decimal(getattr(self, field_name), field_name=field_name),
            )
        if self.error_reason is not None:
            normalized_error = _required_text(self.error_reason, field_name="error_reason")
            object.__setattr__(self, "error_reason", normalized_error)
            if self.allocations or self.transferred_cost_local or self.transferred_cost_base:
                raise ValueError("failed basis transfers cannot carry economics")
            return
        if not self.allocations:
            raise ValueError("successful basis transfer requires source-lot allocations")
        if tuple(allocation.allocation_ordinal for allocation in self.allocations) != tuple(
            range(1, len(self.allocations) + 1)
        ):
            raise ValueError("basis-transfer allocation ordinals must be contiguous")
        source_lot_ids = tuple(allocation.source_lot_id for allocation in self.allocations)
        if len(source_lot_ids) != len(set(source_lot_ids)):
            raise ValueError("a source lot can appear only once in one basis transfer")
        object.__setattr__(self, "calculation_lineage", _build_basis_transfer_lineage(self))

    @classmethod
    def failed(cls, error_reason: str) -> "LotBasisTransferResult":
        return cls(
            transferred_cost_local=Decimal(0),
            transferred_cost_base=Decimal(0),
            allocations=(),
            error_reason=error_reason,
        )


@dataclass(frozen=True, slots=True)
class TransactionLotBasisTransfer:
    """Bind source-lot basis movement to its corporate-action source transaction."""

    source_transaction_id: str
    target_transaction_id: str
    target_lot_id: str
    result: LotBasisTransferResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_transaction_id",
            _required_text(self.source_transaction_id, field_name="source_transaction_id"),
        )
        object.__setattr__(
            self,
            "target_transaction_id",
            _required_text(self.target_transaction_id, field_name="target_transaction_id"),
        )
        object.__setattr__(
            self,
            "target_lot_id",
            _required_text(self.target_lot_id, field_name="target_lot_id"),
        )
        if self.source_transaction_id == self.target_transaction_id:
            raise ValueError("source and target transaction ids must differ")
        if self.target_lot_id != f"LOT-{self.target_transaction_id}":
            raise ValueError("target_lot_id must derive from target_transaction_id")
        if self.result.error_reason is not None:
            raise ValueError("transaction basis-transfer evidence requires a successful result")


def _build_basis_transfer_lineage(result: LotBasisTransferResult) -> CalculationLineage:
    local_total = _sum_amounts(
        tuple(allocation.transferred_cost_local for allocation in result.allocations),
        field_name="transferred_cost_local",
    )
    base_total = _sum_amounts(
        tuple(allocation.transferred_cost_base for allocation in result.allocations),
        field_name="transferred_cost_base",
    )
    if local_total != result.transferred_cost_local:
        raise ValueError("source-lot local basis does not reconcile to transfer aggregate")
    if base_total != result.transferred_cost_base:
        raise ValueError("source-lot base basis does not reconcile to transfer aggregate")
    return build_calculation_lineage(
        algorithm_id=BASIS_TRANSFER_LINEAGE_ALGORITHM_ID,
        algorithm_version=BASIS_TRANSFER_LINEAGE_ALGORITHM_VERSION,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=basis_transfer_lineage_input_payload(result.allocations),
        output_payload=basis_transfer_lineage_output_payload(
            result.allocations,
            transferred_cost_base=result.transferred_cost_base,
            transferred_cost_local=result.transferred_cost_local,
        ),
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    )
