# services/ingestion_service/app/DTOs/transaction_dto.py
from datetime import UTC, date, datetime
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
        json_schema_extra={"example": "AUTO_GENERATE"},
        description=(
            "Cash-leg generation mode. Use AUTO_GENERATE for service-generated cash "
            "leg, or UPSTREAM_PROVIDED when a separate upstream cash entry is "
            "authoritative."
        ),
    )
    external_cash_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CASH-ENTRY-2026-0001"},
        description=(
            "Upstream cash transaction identifier when cash_entry_mode is "
            "UPSTREAM_PROVIDED."
        ),
    )
    settlement_cash_account_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CASH-ACC-USD-001"},
        description=(
            "Settlement cash account identifier used to build the generated "
            "ADJUSTMENT cash leg in AUTO_GENERATE mode."
        ),
    )
    settlement_cash_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CASH-USD"},
        description=(
            "Optional direct cash instrument_id for generated ADJUSTMENT cash legs. "
            "If omitted, engine resolves from settlement_cash_account_id."
        ),
    )
    movement_direction: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "INFLOW"},
        description=(
            "Cash movement direction for ADJUSTMENT transactions. "
            "Supported canonical values are INFLOW and OUTFLOW."
        ),
    )
    originating_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "TRN001"},
        description="Product-leg transaction id linked to an ADJUSTMENT cash leg.",
    )
    originating_transaction_type: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY"},
        description="Product-leg transaction type linked to an ADJUSTMENT cash leg.",
    )
    adjustment_reason: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_SETTLEMENT"},
        description="Canonical reason code describing why an ADJUSTMENT cash leg exists.",
    )
    link_type: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_TO_CASH"},
        description="Canonical relationship label between product leg and ADJUSTMENT cash leg.",
    )
    reconciliation_key: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "REC-2026-0001"},
        description="Optional reconciliation key shared by paired dual-leg transactions.",
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
    parent_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA_PARENT_TXN_001"},
        description="Corporate-action parent transaction reference for child linkage.",
    )
    linked_parent_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-EVT-2026-0001"},
        description="Linked corporate-action parent event identifier.",
    )
    parent_event_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM-CA-REF-2026-0001"},
        description="Upstream parent-event reference shared by all related CA children.",
    )
    child_role: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "SOURCE_POSITION_CLOSE"},
        description="Canonical corporate-action child role for dependency-aware processing.",
    )
    child_sequence_hint: Optional[int] = Field(
        default=None,
        json_schema_extra={"example": 10},
        description="Optional upstream child sequencing hint for deterministic orchestration.",
    )
    dependency_reference_ids: Optional[list[str]] = Field(
        default=None,
        json_schema_extra={"example": ["CA-CHILD-OUT-001"]},
        description="Optional upstream dependency reference ids for child ordering.",
    )
    source_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "OLD_SEC_001"},
        description="Source instrument identifier for transfer-style corporate actions.",
    )
    target_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "NEW_SEC_001"},
        description="Target instrument identifier for transfer-style corporate actions.",
    )
    source_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CHILD-OUT-001"},
        description="Reference to source-side corporate-action child transaction.",
    )
    target_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CHILD-IN-001"},
        description="Reference to target-side corporate-action child transaction.",
    )
    linked_cash_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CIL-CASH-001"},
        description="Linked cash transaction id for CASH_IN_LIEU and related settlement.",
    )
    has_synthetic_flow: Optional[bool] = Field(
        default=None,
        json_schema_extra={"example": True},
        description="Whether this transaction carries a position-level synthetic flow payload.",
    )
    synthetic_flow_effective_date: Optional[date] = Field(
        default=None,
        json_schema_extra={"example": "2026-03-15"},
        description="Synthetic flow effective date for corporate-action analytics.",
    )
    synthetic_flow_amount_local: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "-10000.00"},
        description="Synthetic flow amount in local flow currency.",
    )
    synthetic_flow_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "USD"},
        description="Currency of synthetic flow amount.",
    )
    synthetic_flow_amount_base: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "-10000.00"},
        description="Synthetic flow amount translated into portfolio base currency.",
    )
    synthetic_flow_fx_rate_to_base: Optional[condecimal(gt=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "1.000000"},
        description="FX rate used to derive synthetic_flow_amount_base from local amount.",
    )
    synthetic_flow_price_used: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "200.00"},
        description="Price input used for MVT synthetic flow valuation.",
    )
    synthetic_flow_quantity_used: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "50.00"},
        description="Quantity input used for MVT synthetic flow valuation.",
    )
    synthetic_flow_valuation_method: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "MVT_PRICE_X_QTY"},
        description="Synthetic flow valuation method classification.",
    )
    synthetic_flow_classification: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "POSITION_TRANSFER_OUT"},
        description="Synthetic flow classification for position-level analytics.",
    )
    synthetic_flow_price_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM"},
        description="Synthetic flow price source classification.",
    )
    synthetic_flow_fx_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX_SERVICE"},
        description="Synthetic flow FX source classification.",
    )
    synthetic_flow_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM_PROVIDED"},
        description="Synthetic flow origin descriptor for audit and lineage.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TransactionIngestionRequest(BaseModel):
    transactions: List[Transaction]
