"""Immutable source-lot allocation evidence produced during cost-basis disposal."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
    calculation_lineage_binds_output,
    require_sha256_digest,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
    LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
    canonical_cost_basis_output_payload,
    lot_disposal_allocation_payload,
    lot_disposal_lineage_input_payload,
    lot_disposal_lineage_output_payload,
)
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)


@dataclass(frozen=True, slots=True)
class AmortizedCostAllocationEvidence:
    """Immutable carrying-amount evidence used for one source-lot allocation."""

    profile_id: str
    profile_version: int
    profile_content_hash: str
    currency: str
    disposal_date: date
    recognized_through_date: date
    original_quantity: Decimal
    open_quantity_before: Decimal
    consumed_quantity: Decimal
    residual_quantity: Decimal
    scheduled_cost_local: Decimal
    current_cost_local: Decimal
    current_cost_base: Decimal
    consumed_cost_local: Decimal
    residual_cost_local: Decimal
    book_cost_fx_rate_to_base: Decimal
    consumed_cost_base: Decimal
    residual_cost_base: Decimal
    retained_rounding_residual_local: Decimal
    retained_rounding_residual_base: Decimal
    calculation_lineage: CalculationLineage

    def __post_init__(self) -> None:
        for field_name in ("profile_id", "currency"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        if not isinstance(self.profile_version, int) or isinstance(self.profile_version, bool):
            raise TypeError("profile_version must be an integer")
        if self.profile_version < 1:
            raise ValueError("profile_version must be positive")
        require_sha256_digest(self.profile_content_hash, "profile_content_hash")
        for field_name in ("disposal_date", "recognized_through_date"):
            if type(getattr(self, field_name)) is not date:
                raise TypeError(f"{field_name} must be a date")
        if self.recognized_through_date > self.disposal_date:
            raise ValueError("recognized_through_date must not be after disposal_date")
        for field_name in (
            "original_quantity",
            "open_quantity_before",
            "consumed_quantity",
            "residual_quantity",
            "scheduled_cost_local",
            "current_cost_local",
            "current_cost_base",
            "consumed_cost_local",
            "residual_cost_local",
            "book_cost_fx_rate_to_base",
            "consumed_cost_base",
            "residual_cost_base",
            "retained_rounding_residual_local",
            "retained_rounding_residual_base",
        ):
            _require_decimal(
                getattr(self, field_name),
                field_name,
                positive=field_name
                in {
                    "original_quantity",
                    "open_quantity_before",
                    "consumed_quantity",
                    "book_cost_fx_rate_to_base",
                },
                allow_negative=field_name
                in {
                    "retained_rounding_residual_local",
                    "retained_rounding_residual_base",
                },
            )
        if self.open_quantity_before > self.original_quantity:
            raise ValueError("open_quantity_before must not exceed original_quantity")
        if self.consumed_quantity + self.residual_quantity != self.open_quantity_before:
            raise ValueError("amortized-cost quantity does not conserve the pre-disposal lot")
        if self.consumed_cost_local + self.residual_cost_local != self.current_cost_local:
            raise ValueError("amortized local cost does not conserve current lot cost")
        if self.consumed_cost_base + self.residual_cost_base != self.current_cost_base:
            raise ValueError("amortized base cost does not conserve current lot cost")
        if not isinstance(self.calculation_lineage, CalculationLineage):
            raise TypeError("calculation_lineage must be a CalculationLineage")
        if not calculation_lineage_binds_output(
            self.calculation_lineage,
            output_payload=self.output_payload(),
        ):
            raise ValueError("amortized-cost evidence does not match calculation lineage")

    def output_payload(self) -> dict[str, object]:
        """Return the calculation output bound by the amortized-cost lineage."""

        return cast(
            dict[str, object],
            canonical_cost_basis_output_payload(
                {
                    "consumed_cost_base": self.consumed_cost_base,
                    "consumed_cost_local": self.consumed_cost_local,
                    "consumed_quantity": self.consumed_quantity,
                    "current_cost_base": self.current_cost_base,
                    "current_cost_local": self.current_cost_local,
                    "open_quantity_before": self.open_quantity_before,
                    "recognized_through_date": self.recognized_through_date,
                    "residual_cost_base": self.residual_cost_base,
                    "residual_cost_local": self.residual_cost_local,
                    "residual_quantity": self.residual_quantity,
                    "retained_rounding_residual_base": self.retained_rounding_residual_base,
                    "retained_rounding_residual_local": self.retained_rounding_residual_local,
                    "scheduled_cost_local": self.scheduled_cost_local,
                }
            ),
        )

    def semantic_payload(self) -> dict[str, object]:
        """Return complete profile, allocation, and calculation evidence for persistence."""

        return {
            "calculation_lineage": self.calculation_lineage.lineage_payload(),
            "consumed_cost_base": self.consumed_cost_base,
            "consumed_cost_local": self.consumed_cost_local,
            "consumed_quantity": self.consumed_quantity,
            "currency": self.currency,
            "current_cost_local": self.current_cost_local,
            "current_cost_base": self.current_cost_base,
            "disposal_date": self.disposal_date,
            "book_cost_fx_rate_to_base": self.book_cost_fx_rate_to_base,
            "original_quantity": self.original_quantity,
            "open_quantity_before": self.open_quantity_before,
            "profile_content_hash": self.profile_content_hash,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "recognized_through_date": self.recognized_through_date,
            "residual_cost_base": self.residual_cost_base,
            "residual_cost_local": self.residual_cost_local,
            "residual_quantity": self.residual_quantity,
            "retained_rounding_residual_base": self.retained_rounding_residual_base,
            "retained_rounding_residual_local": self.retained_rounding_residual_local,
            "scheduled_cost_local": self.scheduled_cost_local,
        }


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
    source_original_quantity: Decimal | None = None
    source_open_quantity_before: Decimal | None = None
    amortized_cost_evidence: AmortizedCostAllocationEvidence | None = None

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
        if (self.source_original_quantity is None) != (self.source_open_quantity_before is None):
            raise ValueError("source quantity authority must be complete when supplied")
        source_original_quantity = self.source_original_quantity
        source_open_quantity_before = self.source_open_quantity_before
        if source_original_quantity is not None:
            assert source_open_quantity_before is not None
            _require_decimal(
                source_original_quantity,
                "source_original_quantity",
                positive=True,
            )
            _require_decimal(
                source_open_quantity_before,
                "source_open_quantity_before",
                positive=True,
            )
            if source_open_quantity_before > source_original_quantity:
                raise ValueError("source open quantity must not exceed original quantity")
            if self.consumed_quantity > source_open_quantity_before:
                raise ValueError("consumed quantity must not exceed source open quantity")
        if self.amortized_cost_evidence is not None:
            if not isinstance(self.amortized_cost_evidence, AmortizedCostAllocationEvidence):
                raise TypeError(
                    "amortized_cost_evidence must be an AmortizedCostAllocationEvidence or None"
                )
            if (
                self.amortized_cost_evidence.consumed_quantity != self.consumed_quantity
                or self.amortized_cost_evidence.consumed_cost_local != self.consumed_cost_local
                or self.amortized_cost_evidence.consumed_cost_base != self.consumed_cost_base
            ):
                raise ValueError("amortized-cost evidence must match allocated quantity and cost")


def source_lot_disposal_allocation_payload(
    allocation: SourceLotDisposalAllocation,
) -> dict[str, object]:
    """Return one canonical allocation payload without changing legacy hash identity."""

    if not isinstance(allocation, SourceLotDisposalAllocation):
        raise TypeError("allocation must be a SourceLotDisposalAllocation")
    payload: dict[str, object] = lot_disposal_allocation_payload(
        allocation,
        amortized_cost_evidence=(
            allocation.amortized_cost_evidence.semantic_payload()
            if allocation.amortized_cost_evidence is not None
            else None
        ),
    )
    return payload


@dataclass(frozen=True, slots=True)
class LotDisposalResult:
    """Aggregate cost result plus exact source-lot allocation evidence."""

    cost_base: Decimal
    cost_local: Decimal
    consumed_quantity: Decimal
    allocations: tuple[SourceLotDisposalAllocation, ...]
    error_reason: str | None = None
    calculation_lineage: CalculationLineage | None = field(init=False, default=None)

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
        object.__setattr__(self, "calculation_lineage", _build_conserved_allocation_lineage(self))

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


@dataclass(frozen=True, slots=True)
class TransactionLotDisposal:
    """Bind one successful lot-disposal result to its consuming transaction."""

    disposal_transaction_id: str
    result: LotDisposalResult

    def __post_init__(self) -> None:
        if not isinstance(self.disposal_transaction_id, str):
            raise TypeError("disposal_transaction_id must be a string")
        normalized = self.disposal_transaction_id.strip()
        if not normalized:
            raise ValueError("disposal_transaction_id must be nonblank")
        object.__setattr__(self, "disposal_transaction_id", normalized)
        if not isinstance(self.result, LotDisposalResult):
            raise TypeError("result must be a LotDisposalResult")
        if self.result.error_reason is not None or self.result.consumed_quantity <= Decimal(0):
            raise ValueError("transaction disposal evidence requires a successful positive result")


def _build_conserved_allocation_lineage(result: LotDisposalResult) -> CalculationLineage:
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
    return build_calculation_lineage(
        algorithm_id=LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
        algorithm_version=LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=lot_disposal_lineage_input_payload(
            [
                source_lot_disposal_allocation_payload(allocation)
                for allocation in result.allocations
            ]
        ),
        output_payload=lot_disposal_lineage_output_payload(
            consumed_cost_base=result.cost_base,
            consumed_cost_local=result.cost_local,
            consumed_quantity=result.consumed_quantity,
        ),
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    )


def _require_decimal(
    value: object,
    field_name: str,
    *,
    positive: bool = False,
    allow_negative: bool = False,
) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if (not allow_negative and value < Decimal(0)) or (positive and value == Decimal(0)):
        requirement = "positive" if positive else "non-negative"
        raise ValueError(f"{field_name} must be {requirement}")
