# services/ingestion_service/app/DTOs/transaction_dto.py
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, condecimal


class Transaction(BaseModel):
    transaction_id: str = Field(
        description="Canonical transaction identifier for ingestion, replay, and audit workflows.",
        json_schema_extra={"example": "TRN001"},
    )
    portfolio_id: str = Field(
        description="Canonical portfolio identifier that owns the transaction.",
        json_schema_extra={"example": "PORT001"},
    )
    instrument_id: str = Field(
        description="Canonical instrument identifier associated with the transaction.",
        json_schema_extra={"example": "AAPL"},
    )
    security_id: str = Field(
        description="Canonical security identifier associated with the transaction record.",
        json_schema_extra={"example": "SEC_AAPL"},
    )
    transaction_date: datetime = Field(
        description="Trade or economic timestamp used to order the transaction in the ledger.",
        json_schema_extra={"example": "2023-01-15T10:00:00Z"},
    )
    transaction_type: str = Field(
        description="Canonical transaction type that drives downstream calculator behavior.",
        json_schema_extra={"example": "BUY"},
    )
    quantity: condecimal(ge=Decimal(0)) = Field(
        description="Absolute traded quantity or units moved by the transaction.",
        json_schema_extra={"example": "10.0"},
    )
    price: condecimal(ge=Decimal(0)) = Field(
        description="Per-unit transaction price in the trade currency.",
        json_schema_extra={"example": "150.0"},
    )
    gross_transaction_amount: condecimal(gt=Decimal(0)) = Field(
        description="Gross economic amount before fees, taxes, or deductions.",
        json_schema_extra={"example": "1500.0"}
    )
    trade_currency: str = Field(
        description="Trade currency in which price and gross amount are quoted.",
        json_schema_extra={"example": "USD"},
    )
    currency: str = Field(
        description=(
            "Canonical transaction currency retained for compatibility "
            "with downstream ledgers."
        ),
        json_schema_extra={"example": "USD"},
    )
    trade_fee: Optional[condecimal(ge=Decimal(0))] = Field(
        default=Decimal(0),
        description=(
            "Aggregate trade fee applied to the transaction when fee "
            "breakdown is not split out."
        ),
        json_schema_extra={"example": "5.0"},
    )
    brokerage: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        description=(
            "Brokerage fee component. If provided with other fee components, trade_fee "
            "is recomputed from breakdown."
        ),
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
    settlement_date: Optional[datetime] = Field(
        default=None,
        description=(
            "Optional settlement timestamp used for cash-leg timing and "
            "operations monitoring."
        ),
        json_schema_extra={"example": "2023-01-17T10:00:00Z"},
    )
    economic_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "EVT-2026-00987"},
        description=(
            "Canonical economic event identifier that groups all legs or "
            "components of the same economic workflow."
        ),
    )
    linked_transaction_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "LTG-2026-00456"},
        description=(
            "Canonical linkage group identifier shared by related product "
            "and cash-leg entries."
        ),
    )
    calculation_policy_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_DEFAULT_POLICY"},
        description="Resolved calculation-policy identifier used to process the transaction.",
    )
    calculation_policy_version: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "1.0.0"},
        description="Resolved calculation-policy version used to process the transaction.",
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
            "Cash-leg handling mode. Use AUTO_GENERATE for service-generated "
            "cash legs or UPSTREAM_PROVIDED when the upstream cash entry is authoritative."
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
            "Settlement cash account identifier used to resolve or build the "
            "cash-leg posting destination."
        ),
    )
    settlement_cash_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CASH-USD"},
        description=(
            "Optional direct cash instrument identifier for generated or "
            "linked cash legs. If omitted, the engine resolves from the account mapping."
        ),
    )
    movement_direction: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "INFLOW"},
        description=(
            "Cash movement direction for cash-leg style transactions. "
            "Supported canonical values are INFLOW and OUTFLOW."
        ),
    )
    originating_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "TRN001"},
        description="Product-leg transaction identifier linked to the related cash-leg entry.",
    )
    originating_transaction_type: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY"},
        description="Product-leg transaction type linked to the related cash-leg entry.",
    )
    adjustment_reason: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_SETTLEMENT"},
        description="Canonical reason code describing why the cash-leg entry exists.",
    )
    link_type: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_TO_CASH"},
        description="Canonical relationship label between product and cash-leg entries.",
    )
    reconciliation_key: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "REC-2026-0001"},
        description=(
            "Optional reconciliation key shared by paired or grouped "
            "dual-leg transactions."
        ),
    )
    interest_direction: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "INCOME"},
        description=(
            "Semantic direction for INTEREST transactions. Supported values are "
            "INCOME and EXPENSE."
        ),
    )
    withholding_tax_amount: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "15.25"},
        description="Withholding tax amount applied to the interest transaction.",
    )
    other_interest_deductions_amount: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "1.00"},
        description="Other non-tax deductions applied to the interest transaction.",
    )
    net_interest_amount: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "108.20"},
        description=(
            "Net interest amount supplied upstream for reconciliation against "
            "gross and deduction fields."
        ),
    )
    component_type: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX_CASH_SETTLEMENT_BUY"},
        description=(
            "Canonical FX component type when transaction_type is FX_SPOT, "
            "FX_FORWARD, or FX_SWAP."
        ),
    )
    component_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-COMP-0001"},
        description="Unique FX component identifier within the linked transaction group.",
    )
    linked_component_ids: Optional[list[str]] = Field(
        default=None,
        json_schema_extra={"example": ["FX-COMP-0002", "FX-COMP-0003"]},
        description="Other FX component identifiers linked to this transaction component.",
    )
    fx_cash_leg_role: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY"},
        description="Canonical FX cash-leg role. Supported values are BUY and SELL.",
    )
    linked_fx_cash_leg_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-SETTLE-SELL-0001"},
        description="Opposite FX cash settlement transaction identifier.",
    )
    settlement_status: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "PENDING"},
        description="Settlement status for FX cash settlement components.",
    )
    pair_base_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "EUR"},
        description="Base currency of the quoted FX pair.",
    )
    pair_quote_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "USD"},
        description="Quote currency of the quoted FX pair.",
    )
    fx_rate_quote_convention: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "QUOTE_PER_BASE"},
        description="Explicit FX quote convention for interpreting contract_rate.",
    )
    buy_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "USD"},
        description="Currency bought/received by the FX transaction.",
    )
    sell_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "EUR"},
        description="Currency sold/delivered by the FX transaction.",
    )
    buy_amount: Optional[condecimal(gt=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "1095000"},
        description="Positive magnitude of currency bought.",
    )
    sell_amount: Optional[condecimal(gt=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "1000000"},
        description="Positive magnitude of currency sold.",
    )
    contract_rate: Optional[condecimal(gt=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "1.095"},
        description="Contractual FX rate for the deal.",
    )
    fx_contract_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXC-2026-0001"},
        description="Stable FX contract identifier for forwards/swaps and spot-under-policy.",
    )
    fx_contract_open_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-OPEN-0001"},
        description="Linked FX contract-open transaction identifier.",
    )
    fx_contract_close_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-CLOSE-0001"},
        description="Linked FX contract-close transaction identifier.",
    )
    settlement_of_fx_contract_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXC-2026-0001"},
        description="FX contract identifier settled by this cash component.",
    )
    swap_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001"},
        description="Stable FX swap event identifier.",
    )
    near_leg_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001-NEAR"},
        description="Near-leg linkage group identifier for FX swaps.",
    )
    far_leg_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001-FAR"},
        description="Far-leg linkage group identifier for FX swaps.",
    )
    spot_exposure_model: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "NONE"},
        description="Policy-driven spot exposure model. Supported values are NONE and FX_CONTRACT.",
    )
    fx_realized_pnl_mode: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM_PROVIDED"},
        description="Policy-driven realized FX P&L mode.",
    )
    realized_capital_pnl_local: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "0.00"},
        description="Realized capital P&L in local currency. Must be explicit zero for FX.",
    )
    realized_fx_pnl_local: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description="Realized FX P&L in local currency.",
    )
    realized_total_pnl_local: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description="Total realized P&L in local currency.",
    )
    realized_capital_pnl_base: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "0.00"},
        description="Realized capital P&L in base currency. Must be explicit zero for FX.",
    )
    realized_fx_pnl_base: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description="Realized FX P&L in base currency.",
    )
    realized_total_pnl_base: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description="Total realized P&L in base currency.",
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
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Ingestion-side creation timestamp for lineage and troubleshooting.",
        json_schema_extra={"example": "2026-03-10T11:32:15Z"},
    )


class TransactionIngestionRequest(BaseModel):
    transactions: List[Transaction] = Field(
        ...,
        description="Canonical transaction records to ingest or upsert asynchronously.",
        min_length=1,
        examples=[
            [
                {
                    "transaction_id": "TRN001",
                    "portfolio_id": "PORT001",
                    "instrument_id": "AAPL",
                    "security_id": "SEC_AAPL",
                    "transaction_date": "2023-01-15T10:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": "10.0",
                    "price": "150.0",
                    "gross_transaction_amount": "1500.0",
                    "trade_currency": "USD",
                    "currency": "USD",
                    "trade_fee": "5.0",
                    "settlement_date": "2023-01-17T10:00:00Z",
                }
            ]
        ],
    )
