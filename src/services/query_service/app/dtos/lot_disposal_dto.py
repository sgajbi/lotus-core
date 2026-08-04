"""Transaction-neutral immutable lot-disposal receipt API contracts."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class LotDisposalAllocationResponse(BaseModel):
    allocation_ordinal: int = Field(..., ge=1)
    source_lot_id: str
    source_transaction_id: str
    source_acquisition_date: date
    consumed_quantity: Decimal
    consumed_cost_local: Decimal
    consumed_cost_base: Decimal
    allocation_content_hash: str
    amortized_cost_profile_id: str | None = None
    amortized_cost_profile_version: int | None = None
    amortized_cost_profile_content_hash: str | None = None
    amortized_cost_recognized_through: date | None = None
    amortized_cost_calculation_lineage: dict[str, Any] | None = None


class LotDisposalReceiptResponse(BaseModel):
    receipt_id: str
    receipt_version: int = Field(..., ge=1)
    disposal_transaction_id: str
    portfolio_id: str
    instrument_id: str
    security_id: str
    disposal_timestamp: datetime
    transaction_type: str
    cost_basis_method: str
    calculation_policy_id: str | None = None
    calculation_policy_version: str | None = None
    status: str
    void_reason: str | None = None
    consumed_quantity: Decimal
    consumed_cost_local: Decimal
    consumed_cost_base: Decimal
    semantic_content_hash: str
    previous_receipt_content_hash: str | None = None
    receipt_content_hash: str
    transaction_calculation_lineage: dict[str, Any]
    disposal_calculation_lineage: dict[str, Any] | None = None
    allocations: list[LotDisposalAllocationResponse]
