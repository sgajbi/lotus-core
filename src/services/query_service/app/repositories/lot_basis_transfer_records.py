"""Persistence-neutral immutable lot basis-transfer read records."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class LotBasisTransferReceiptReadRecord:
    receipt_id: str
    receipt_version: int
    source_transaction_id: str
    target_transaction_id: str
    target_lot_id: str
    portfolio_id: str
    source_instrument_id: str
    source_security_id: str
    target_instrument_id: str | None
    transfer_timestamp: datetime
    transaction_type: str
    cost_basis_method: str
    calculation_policy_id: str | None
    calculation_policy_version: str | None
    status: str
    void_reason: str | None
    transferred_cost_local: Decimal
    transferred_cost_base: Decimal
    allocation_count: int
    semantic_content_hash: str
    previous_receipt_content_hash: str | None
    receipt_content_hash: str
    transaction_calculation_lineage: dict[str, Any]
    basis_transfer_calculation_lineage: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class LotBasisTransferAllocationReadRecord:
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
    allocation_content_hash: str
