"""Version-independent immutable state for one transaction lot-disposal receipt."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from .calculation.disposal_allocation import (
    SourceLotDisposalAllocation,
    source_lot_disposal_allocation_payload,
)
from .state_lineage import canonical_cost_basis_output_payload


class LotDisposalReceiptStatus(StrEnum):
    """Auditable state of the latest receipt version for one transaction."""

    ACTIVE = "ACTIVE"
    VOIDED = "VOIDED"


@dataclass(frozen=True, slots=True)
class LotDisposalReceiptState:
    """Closed semantic payload from which immutable receipt versions are appended."""

    disposal_transaction_id: str
    portfolio_id: str
    instrument_id: str
    security_id: str
    disposal_timestamp: datetime
    transaction_type: str
    cost_basis_method: CostBasisMethod
    calculation_policy_id: str | None
    calculation_policy_version: str | None
    transaction_calculation_lineage: CalculationLineage
    status: LotDisposalReceiptStatus
    consumed_quantity: Decimal
    consumed_cost_local: Decimal
    consumed_cost_base: Decimal
    allocations: tuple[SourceLotDisposalAllocation, ...]
    disposal_calculation_lineage: CalculationLineage | None
    void_reason: str | None = None
    receipt_id: str = field(init=False)
    semantic_content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for field_name in (
            "disposal_transaction_id",
            "portfolio_id",
            "instrument_id",
            "security_id",
            "transaction_type",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        if not isinstance(self.disposal_timestamp, datetime):
            raise TypeError("disposal_timestamp must be a datetime")
        if self.disposal_timestamp.tzinfo is None or self.disposal_timestamp.utcoffset() is None:
            raise ValueError("disposal_timestamp must be timezone-aware")
        if not isinstance(self.cost_basis_method, CostBasisMethod):
            raise TypeError("cost_basis_method must be a CostBasisMethod")
        _normalize_optional_policy(self, "calculation_policy_id")
        _normalize_optional_policy(self, "calculation_policy_version")
        if (self.calculation_policy_id is None) != (self.calculation_policy_version is None):
            raise ValueError("calculation policy ID and version must be supplied together")
        if not isinstance(self.transaction_calculation_lineage, CalculationLineage):
            raise TypeError("transaction_calculation_lineage must be a CalculationLineage")
        if not isinstance(self.status, LotDisposalReceiptStatus):
            raise TypeError("status must be a LotDisposalReceiptStatus")
        for field_name in (
            "consumed_quantity",
            "consumed_cost_local",
            "consumed_cost_base",
        ):
            _require_nonnegative_decimal(getattr(self, field_name), field_name)
        if not isinstance(self.allocations, tuple) or not all(
            isinstance(allocation, SourceLotDisposalAllocation) for allocation in self.allocations
        ):
            raise TypeError("allocations must be a tuple of SourceLotDisposalAllocation")
        self._validate_lifecycle_shape()
        identity_hash = canonical_content_hash(
            {
                "disposal_transaction_id": self.disposal_transaction_id,
                "portfolio_id": self.portfolio_id,
                "security_id": self.security_id,
            }
        )
        object.__setattr__(self, "receipt_id", f"lot-disposal:{identity_hash}")
        object.__setattr__(
            self,
            "semantic_content_hash",
            canonical_content_hash(self.semantic_payload()),
        )

    @property
    def allocation_count(self) -> int:
        """Return the exact number of ordered source-lot allocation rows."""

        return len(self.allocations)

    def semantic_payload(self) -> dict[str, object]:
        """Return the closed payload compared for replay and correction semantics."""

        return cast(
            dict[str, object],
            canonical_cost_basis_output_payload(
                {
                    "allocations": [
                        source_lot_disposal_allocation_payload(allocation)
                        for allocation in self.allocations
                    ],
                    "calculation_policy_id": self.calculation_policy_id,
                    "calculation_policy_version": self.calculation_policy_version,
                    "consumed_cost_base": self.consumed_cost_base,
                    "consumed_cost_local": self.consumed_cost_local,
                    "consumed_quantity": self.consumed_quantity,
                    "cost_basis_method": self.cost_basis_method.value,
                    "disposal_calculation_lineage": (
                        self.disposal_calculation_lineage.lineage_payload()
                        if self.disposal_calculation_lineage is not None
                        else None
                    ),
                    "disposal_timestamp": self.disposal_timestamp,
                    "disposal_transaction_id": self.disposal_transaction_id,
                    "instrument_id": self.instrument_id,
                    "portfolio_id": self.portfolio_id,
                    "security_id": self.security_id,
                    "status": self.status.value,
                    "transaction_calculation_lineage": (
                        self.transaction_calculation_lineage.lineage_payload()
                    ),
                    "transaction_type": self.transaction_type,
                    "void_reason": self.void_reason,
                }
            ),
        )

    def _validate_lifecycle_shape(self) -> None:
        if self.status is LotDisposalReceiptStatus.ACTIVE:
            if self.consumed_quantity <= Decimal(0) or not self.allocations:
                raise ValueError("active disposal receipt must carry positive allocations")
            if self.disposal_calculation_lineage is None:
                raise ValueError("active disposal receipt requires disposal calculation lineage")
            if self.void_reason is not None:
                raise ValueError("active disposal receipt cannot carry a void reason")
            self._validate_active_allocations()
            return
        if (
            any(
                (
                    self.consumed_quantity,
                    self.consumed_cost_local,
                    self.consumed_cost_base,
                )
            )
            or self.allocations
        ):
            raise ValueError("voided disposal receipt cannot carry economics or allocations")
        if self.disposal_calculation_lineage is not None:
            raise ValueError("voided disposal receipt cannot carry disposal lineage")
        if not isinstance(self.void_reason, str) or not self.void_reason.strip():
            raise ValueError("voided disposal receipt requires a nonblank reason")
        object.__setattr__(self, "void_reason", self.void_reason.strip())

    def _validate_active_allocations(self) -> None:
        ordinals = tuple(allocation.allocation_ordinal for allocation in self.allocations)
        if ordinals != tuple(range(1, len(self.allocations) + 1)):
            raise ValueError("receipt allocation ordinals must be contiguous from one")
        source_lot_ids = tuple(allocation.source_lot_id for allocation in self.allocations)
        if len(set(source_lot_ids)) != len(source_lot_ids):
            raise ValueError("receipt source lots must be unique")
        quantity = sum(
            (allocation.consumed_quantity for allocation in self.allocations),
            start=Decimal(0),
        )
        cost_local = sum(
            (allocation.consumed_cost_local for allocation in self.allocations),
            start=Decimal(0),
        )
        cost_base = sum(
            (allocation.consumed_cost_base for allocation in self.allocations),
            start=Decimal(0),
        )
        if quantity != self.consumed_quantity:
            raise ValueError("receipt allocation quantity does not reconcile")
        if cost_local != self.consumed_cost_local:
            raise ValueError("receipt allocation local cost does not reconcile")
        if cost_base != self.consumed_cost_base:
            raise ValueError("receipt allocation base cost does not reconcile")


def _normalize_optional_policy(receipt: LotDisposalReceiptState, field_name: str) -> None:
    value = getattr(receipt, field_name)
    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    object.__setattr__(receipt, field_name, normalized or None)


def _require_nonnegative_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite() or value < Decimal(0):
        raise ValueError(f"{field_name} must be finite and non-negative")
