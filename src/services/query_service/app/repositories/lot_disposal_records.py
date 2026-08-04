"""Persistence-neutral immutable lot-disposal read records."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class LotDisposalReceiptReadRecord:
    receipt_id: str
    receipt_version: int
    disposal_transaction_id: str
    portfolio_id: str
    instrument_id: str
    security_id: str
    disposal_timestamp: datetime
    transaction_type: str
    cost_basis_method: str
    calculation_policy_id: str | None
    calculation_policy_version: str | None
    status: str
    void_reason: str | None
    consumed_quantity: Decimal
    consumed_cost_local: Decimal
    consumed_cost_base: Decimal
    semantic_content_hash: str
    previous_receipt_content_hash: str | None
    receipt_content_hash: str
    transaction_calculation_lineage: dict[str, Any]
    disposal_calculation_lineage: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class LotDisposalAllocationReadRecord:
    allocation_ordinal: int
    source_lot_id: str
    source_transaction_id: str
    source_acquisition_date: date
    consumed_quantity: Decimal
    consumed_cost_local: Decimal
    consumed_cost_base: Decimal
    allocation_content_hash: str
    amortized_cost_profile_id: str | None
    amortized_cost_profile_version: int | None
    amortized_cost_profile_content_hash: str | None
    amortized_cost_recognized_through: date | None
    amortized_cost_calculation_lineage: dict[str, Any] | None
