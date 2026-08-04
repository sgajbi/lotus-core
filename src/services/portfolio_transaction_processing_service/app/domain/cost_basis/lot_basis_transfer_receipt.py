"""Immutable receipt state for basis-only source-to-target lot movements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast

from portfolio_common.domain.calculation_lineage import CalculationLineage, canonical_content_hash
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from .calculation.basis_transfer_allocation import SourceLotBasisTransferAllocation
from .state_lineage import canonical_cost_basis_output_payload


class LotBasisTransferReceiptStatus(StrEnum):
    """Auditable state of the latest basis-transfer receipt version."""

    ACTIVE = "ACTIVE"
    VOIDED = "VOIDED"


@dataclass(frozen=True, slots=True)
class LotBasisTransferReceiptState:
    """Closed semantic payload used to append one basis-transfer receipt version."""

    source_transaction_id: str
    target_transaction_id: str
    target_lot_id: str
    portfolio_id: str
    source_instrument_id: str
    source_security_id: str
    target_instrument_id: str | None
    transfer_timestamp: datetime
    transaction_type: str
    cost_basis_method: CostBasisMethod
    calculation_policy_id: str | None
    calculation_policy_version: str | None
    transaction_calculation_lineage: CalculationLineage
    status: LotBasisTransferReceiptStatus
    transferred_cost_local: Decimal
    transferred_cost_base: Decimal
    allocations: tuple[SourceLotBasisTransferAllocation, ...]
    basis_transfer_calculation_lineage: CalculationLineage | None
    void_reason: str | None = None
    receipt_id: str = field(init=False)
    semantic_content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for field_name in (
            "source_transaction_id",
            "target_transaction_id",
            "target_lot_id",
            "portfolio_id",
            "source_instrument_id",
            "source_security_id",
            "transaction_type",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        if self.source_transaction_id == self.target_transaction_id:
            raise ValueError("source and target transaction ids must differ")
        if self.target_lot_id != f"LOT-{self.target_transaction_id}":
            raise ValueError("target_lot_id must derive from target_transaction_id")
        if self.target_instrument_id is not None:
            if not isinstance(self.target_instrument_id, str):
                raise TypeError("target_instrument_id must be a string or None")
            normalized_target_instrument = self.target_instrument_id.strip()
            object.__setattr__(
                self,
                "target_instrument_id",
                normalized_target_instrument or None,
            )
        if not isinstance(self.transfer_timestamp, datetime):
            raise TypeError("transfer_timestamp must be a datetime")
        if self.transfer_timestamp.tzinfo is None or self.transfer_timestamp.utcoffset() is None:
            raise ValueError("transfer_timestamp must be timezone-aware")
        if not isinstance(self.cost_basis_method, CostBasisMethod):
            raise TypeError("cost_basis_method must be a CostBasisMethod")
        self._normalize_optional_policy("calculation_policy_id")
        self._normalize_optional_policy("calculation_policy_version")
        if (self.calculation_policy_id is None) != (self.calculation_policy_version is None):
            raise ValueError("calculation policy ID and version must be supplied together")
        if not isinstance(self.transaction_calculation_lineage, CalculationLineage):
            raise TypeError("transaction_calculation_lineage must be a CalculationLineage")
        if not isinstance(self.status, LotBasisTransferReceiptStatus):
            raise TypeError("status must be a LotBasisTransferReceiptStatus")
        self._require_nonnegative_decimal(self.transferred_cost_local, "transferred_cost_local")
        self._require_nonnegative_decimal(self.transferred_cost_base, "transferred_cost_base")
        if not isinstance(self.allocations, tuple) or not all(
            isinstance(allocation, SourceLotBasisTransferAllocation)
            for allocation in self.allocations
        ):
            raise TypeError("allocations must be a tuple of SourceLotBasisTransferAllocation")
        self._validate_lifecycle_shape()
        identity_hash = canonical_content_hash(
            {
                "portfolio_id": self.portfolio_id,
                "source_security_id": self.source_security_id,
                "source_transaction_id": self.source_transaction_id,
            }
        )
        object.__setattr__(self, "receipt_id", f"lot-basis-transfer:{identity_hash}")
        object.__setattr__(
            self, "semantic_content_hash", canonical_content_hash(self.semantic_payload())
        )

    @property
    def allocation_count(self) -> int:
        return len(self.allocations)

    def semantic_payload(self) -> dict[str, object]:
        return cast(
            dict[str, object],
            canonical_cost_basis_output_payload(
                {
                    "allocations": [self._allocation_payload(value) for value in self.allocations],
                    "basis_transfer_calculation_lineage": (
                        self.basis_transfer_calculation_lineage.lineage_payload()
                        if self.basis_transfer_calculation_lineage is not None
                        else None
                    ),
                    "calculation_policy_id": self.calculation_policy_id,
                    "calculation_policy_version": self.calculation_policy_version,
                    "cost_basis_method": self.cost_basis_method.value,
                    "portfolio_id": self.portfolio_id,
                    "source_instrument_id": self.source_instrument_id,
                    "source_security_id": self.source_security_id,
                    "source_transaction_id": self.source_transaction_id,
                    "status": self.status.value,
                    "target_lot_id": self.target_lot_id,
                    "target_instrument_id": self.target_instrument_id,
                    "target_transaction_id": self.target_transaction_id,
                    "transaction_calculation_lineage": (
                        self.transaction_calculation_lineage.lineage_payload()
                    ),
                    "transaction_type": self.transaction_type,
                    "transfer_timestamp": self.transfer_timestamp,
                    "transferred_cost_base": self.transferred_cost_base,
                    "transferred_cost_local": self.transferred_cost_local,
                    "void_reason": self.void_reason,
                }
            ),
        )

    def _validate_lifecycle_shape(self) -> None:
        if self.status is LotBasisTransferReceiptStatus.ACTIVE:
            if not self.allocations:
                raise ValueError("active basis-transfer receipt requires allocations")
            if self.transferred_cost_local.is_zero() and self.transferred_cost_base.is_zero():
                raise ValueError("active basis-transfer receipt requires positive basis movement")
            if self.basis_transfer_calculation_lineage is None:
                raise ValueError("active basis-transfer receipt requires calculation lineage")
            if self.void_reason is not None:
                raise ValueError("active basis-transfer receipt cannot carry a void reason")
            ordinals = tuple(value.allocation_ordinal for value in self.allocations)
            if ordinals != tuple(range(1, len(self.allocations) + 1)):
                raise ValueError("receipt allocation ordinals must be contiguous from one")
            source_lot_ids = tuple(value.source_lot_id for value in self.allocations)
            if len(source_lot_ids) != len(set(source_lot_ids)):
                raise ValueError("receipt source lots must be unique")
            if (
                sum((value.transferred_cost_local for value in self.allocations), Decimal(0))
                != self.transferred_cost_local
            ):
                raise ValueError("receipt allocation local basis does not reconcile")
            if (
                sum((value.transferred_cost_base for value in self.allocations), Decimal(0))
                != self.transferred_cost_base
            ):
                raise ValueError("receipt allocation base basis does not reconcile")
            return
        if self.transferred_cost_local or self.transferred_cost_base or self.allocations:
            raise ValueError("voided basis-transfer receipt cannot carry economics or allocations")
        if self.basis_transfer_calculation_lineage is not None:
            raise ValueError("voided basis-transfer receipt cannot carry calculation lineage")
        if not isinstance(self.void_reason, str) or not self.void_reason.strip():
            raise ValueError("voided basis-transfer receipt requires a nonblank reason")
        object.__setattr__(self, "void_reason", self.void_reason.strip())

    def _normalize_optional_policy(self, field_name: str) -> None:
        value = getattr(self, field_name)
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string or None")
        object.__setattr__(self, field_name, value.strip() or None)

    @staticmethod
    def _require_nonnegative_decimal(value: object, field_name: str) -> None:
        if not isinstance(value, Decimal):
            raise TypeError(f"{field_name} must be a Decimal")
        if not value.is_finite() or value < Decimal(0):
            raise ValueError(f"{field_name} must be finite and non-negative")

    @staticmethod
    def _allocation_payload(allocation: SourceLotBasisTransferAllocation) -> dict[str, object]:
        return {
            "allocation_ordinal": allocation.allocation_ordinal,
            "retained_cost_base": allocation.retained_cost_base,
            "retained_cost_local": allocation.retained_cost_local,
            "retained_quantity": allocation.retained_quantity,
            "source_acquisition_date": allocation.source_acquisition_date,
            "source_cost_base_before": allocation.source_cost_base_before,
            "source_cost_local_before": allocation.source_cost_local_before,
            "source_lot_id": allocation.source_lot_id,
            "source_transaction_id": allocation.source_transaction_id,
            "transferred_cost_base": allocation.transferred_cost_base,
            "transferred_cost_local": allocation.transferred_cost_local,
        }
