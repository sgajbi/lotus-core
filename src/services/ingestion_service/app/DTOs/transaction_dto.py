# services/ingestion_service/app/DTOs/transaction_dto.py
from datetime import UTC, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, condecimal


class Transaction(BaseModel):
    transaction_id: str = Field(json_schema_extra={"example": "TRN001"})
    portfolio_id: str = Field(json_schema_extra={"example": "PORT001"})
    instrument_id: str = Field(json_schema_extra={"example": "AAPL"})
    security_id: str = Field(json_schema_extra={"example": "SEC_AAPL"})
    transaction_date: datetime = Field(
        json_schema_extra={"example": "2023-01-15T10:00:00Z"}
    )
    transaction_type: str = Field(json_schema_extra={"example": "BUY"})
    quantity: condecimal(ge=Decimal(0)) = Field(json_schema_extra={"example": "10.0"})
    price: condecimal(ge=Decimal(0)) = Field(json_schema_extra={"example": "150.0"})
    gross_transaction_amount: condecimal(gt=Decimal(0)) = Field(
        json_schema_extra={"example": "1500.0"}
    )
    trade_currency: str = Field(json_schema_extra={"example": "USD"})
    currency: str = Field(json_schema_extra={"example": "USD"})
    trade_fee: Optional[condecimal(ge=Decimal(0))] = Field(
        default=Decimal(0), json_schema_extra={"example": "5.0"}
    )
    brokerage: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        description="Brokerage fee component. If provided with other fee components, trade_fee is recomputed from breakdown.",
        json_schema_extra={"example": "2.50"},
    )
    stamp_duty: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        description="Stamp duty fee component.",
        json_schema_extra={"example": "1.20"},
    )
    exchange_fee: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        description="Exchange fee component.",
        json_schema_extra={"example": "0.70"},
    )
    gst: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        description="Goods and services tax fee component.",
        json_schema_extra={"example": "0.45"},
    )
    other_fees: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        description="Other fee components not covered by standard fields.",
        json_schema_extra={"example": "0.15"},
    )
    settlement_date: Optional[datetime] = None
    economic_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "EVT-2026-00987"},
        description=(
            "Canonical economic event identifier. Optional in Slice 1, "
            "planned to become required in strict canonical mode."
        ),
    )
    linked_transaction_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "LTG-2026-00456"},
        description=(
            "Canonical linkage group identifier for related entries. "
            "Optional in Slice 1."
        ),
    )
    calculation_policy_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_DEFAULT_POLICY"},
        description="Resolved BUY policy identifier. Optional in Slice 1.",
    )
    calculation_policy_version: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "1.0.0"},
        description="Resolved BUY policy version. Optional in Slice 1.",
    )
    source_system: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "OMS_PRIMARY"},
        description="Upstream source-system identifier for lineage.",
    )
    cash_entry_mode: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "AUTO"},
        description=(
            "Cash-leg generation mode. Use AUTO for service-generated cash leg, "
            "or EXTERNAL when a separate upstream cash entry is authoritative."
        ),
    )
    external_cash_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CASH-ENTRY-2026-0001"},
        description=(
            "Upstream cash transaction identifier when cash_entry_mode is EXTERNAL."
        ),
    )
    interest_direction: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "INCOME"},
        description=(
            "Optional INTEREST semantic direction. Supported canonical values are "
            "INCOME and EXPENSE."
        ),
    )
    withholding_tax_amount: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "15.25"},
        description="Optional withholding tax amount for INTEREST transactions.",
    )
    other_interest_deductions_amount: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "1.00"},
        description="Optional non-tax deductions applied to INTEREST transactions.",
    )
    net_interest_amount: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "108.20"},
        description=(
            "Optional net-interest amount supplied upstream for reconciliation "
            "against gross and deduction fields."
        ),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TransactionIngestionRequest(BaseModel):
    transactions: List[Transaction]
