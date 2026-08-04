"""Immutable lot basis-transfer supportability API contracts."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class LotBasisTransferAllocationResponse(BaseModel):
    allocation_ordinal: int = Field(..., ge=1)
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


class LotBasisTransferReceiptResponse(BaseModel):
    receipt_id: str
    receipt_version: int = Field(..., ge=1)
    source_transaction_id: str
    target_transaction_id: str
    target_lot_id: str
    portfolio_id: str
    source_instrument_id: str
    source_security_id: str
    target_instrument_id: str | None = None
    transfer_timestamp: datetime
    transaction_type: str
    cost_basis_method: str
    calculation_policy_id: str | None = None
    calculation_policy_version: str | None = None
    status: str
    void_reason: str | None = None
    transferred_cost_local: Decimal
    transferred_cost_base: Decimal
    allocation_count: int = Field(..., ge=0)
    semantic_content_hash: str
    previous_receipt_content_hash: str | None = None
    receipt_content_hash: str
    transaction_calculation_lineage: dict[str, Any]
    basis_transfer_calculation_lineage: dict[str, Any] | None = None
    allocations: list[LotBasisTransferAllocationResponse]
