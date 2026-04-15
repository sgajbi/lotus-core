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
        json_schema_extra={"example": "1500.0"},
    )
    trade_currency: str = Field(
        description="Trade currency in which price and gross amount are quoted.",
        json_schema_extra={"example": "USD"},
    )
    currency: str = Field(
        description=(
            "Canonical transaction currency retained for compatibility with downstream ledgers."
        ),
        json_schema_extra={"example": "USD"},
    )
    transaction_fx_rate: Optional[condecimal(gt=Decimal(0))] = Field(
        default=None,
        description=(
            "Historical FX rate used to translate the transaction from trade currency into "
            "portfolio base currency when the transaction is cross-currency."
        ),
        json_schema_extra={"example": "1.074352"},
    )
    trade_fee: Optional[condecimal(ge=Decimal(0))] = Field(
        default=Decimal(0),
        description=(
            "Aggregate trade fee applied to the transaction when fee breakdown is not split out."
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
            "Optional settlement timestamp used for cash-leg timing and operations monitoring."
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
            "Canonical linkage group identifier shared by related product and cash-leg entries."
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
            "Upstream cash transaction identifier when cash_entry_mode is UPSTREAM_PROVIDED."
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
            "Optional reconciliation key shared by paired or grouped dual-leg transactions."
        ),
    )
    interest_direction: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "INCOME"},
        description=(
            "Semantic direction for INTEREST transactions. Supported values are INCOME and EXPENSE."
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
            "Canonical FX component role within the economic event, such as "
            "cash settlement or contract open/close."
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
        description=(
            "Canonical FX settlement-leg direction for the cash component. "
            "Supported values are BUY and SELL."
        ),
    )
    linked_fx_cash_leg_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-SETTLE-SELL-0001"},
        description="Opposite FX cash settlement transaction identifier.",
    )
    settlement_status: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "PENDING"},
        description=(
            "Settlement lifecycle status for FX cash-settlement components, "
            "for example PENDING or SETTLED."
        ),
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
        description=(
            "Explicit quote convention used to interpret contract_rate, for example QUOTE_PER_BASE."
        ),
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
        description=(
            "Contractual FX rate agreed for the deal, interpreted using fx_rate_quote_convention."
        ),
    )
    fx_contract_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXC-2026-0001"},
        description=(
            "Stable FX contract identifier used to group open, close, and "
            "settlement components for the same forward or swap contract."
        ),
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
        description=(
            "FX contract identifier whose settlement obligation is being "
            "discharged by this cash component."
        ),
    )
    swap_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001"},
        description=(
            "Stable economic event identifier shared by all legs and "
            "settlement components of the same FX swap."
        ),
    )
    near_leg_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001-NEAR"},
        description=(
            "Linkage group identifier for the near leg of an FX swap, used to "
            "tie together its product and settlement components."
        ),
    )
    far_leg_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001-FAR"},
        description=(
            "Linkage group identifier for the far leg of an FX swap, used to "
            "tie together its product and settlement components."
        ),
    )
    spot_exposure_model: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "NONE"},
        description=(
            "Policy-driven spot exposure model. Supported values are NONE and FX_CONTRACT."
        ),
    )
    fx_realized_pnl_mode: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM_PROVIDED"},
        description=(
            "Policy-driven mode for realized FX P&L population, for example "
            "NONE or UPSTREAM_PROVIDED."
        ),
    )
    realized_capital_pnl_local: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "0.00"},
        description=(
            "Realized capital P&L in local currency. Under the canonical FX "
            "model this is expected to remain explicit zero."
        ),
    )
    realized_fx_pnl_local: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description=(
            "Realized FX P&L in local currency for the transaction or settlement component."
        ),
    )
    realized_total_pnl_local: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description=(
            "Total realized P&L in local currency after combining capital and FX components."
        ),
    )
    realized_capital_pnl_base: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "0.00"},
        description=(
            "Realized capital P&L translated into portfolio base currency. "
            "Under the canonical FX model this is expected to remain explicit zero."
        ),
    )
    realized_fx_pnl_base: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description=("Realized FX P&L translated into portfolio base currency."),
    )
    realized_total_pnl_base: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description=("Total realized P&L translated into portfolio base currency."),
    )
    parent_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA_PARENT_TXN_001"},
        description=(
            "Corporate-action parent transaction reference used to link child "
            "transactions back to the upstream parent instruction."
        ),
    )
    linked_parent_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-EVT-2026-0001"},
        description=(
            "Canonical parent corporate-action event identifier shared by all "
            "child transactions created from the same event."
        ),
    )
    parent_event_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM-CA-REF-2026-0001"},
        description=(
            "Upstream parent-event reference shared by all related "
            "corporate-action child transactions."
        ),
    )
    child_role: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "SOURCE_POSITION_CLOSE"},
        description=(
            "Canonical corporate-action child role used to drive dependency-aware "
            "processing and downstream calculator interpretation."
        ),
    )
    child_sequence_hint: Optional[int] = Field(
        default=None,
        json_schema_extra={"example": 10},
        description=(
            "Optional upstream sequencing hint used to preserve deterministic "
            "ordering between related corporate-action child transactions."
        ),
    )
    dependency_reference_ids: Optional[list[str]] = Field(
        default=None,
        json_schema_extra={"example": ["CA-CHILD-OUT-001"]},
        description=(
            "Optional upstream dependency reference identifiers that must be "
            "resolved before this child transaction is processed."
        ),
    )
    source_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "OLD_SEC_001"},
        description=(
            "Source instrument identifier for transfer, replacement, or "
            "exchange-style corporate actions."
        ),
    )
    target_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "NEW_SEC_001"},
        description=(
            "Target instrument identifier for transfer, replacement, or "
            "exchange-style corporate actions."
        ),
    )
    source_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CHILD-OUT-001"},
        description=(
            "Reference to the source-side corporate-action child transaction "
            "within the same parent event."
        ),
    )
    target_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CHILD-IN-001"},
        description=(
            "Reference to the target-side corporate-action child transaction "
            "within the same parent event."
        ),
    )
    linked_cash_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CIL-CASH-001"},
        description=(
            "Linked cash transaction identifier used for cash-in-lieu or "
            "other corporate-action settlement entries."
        ),
    )
    has_synthetic_flow: Optional[bool] = Field(
        default=None,
        json_schema_extra={"example": True},
        description=(
            "Whether this transaction carries a position-level synthetic flow "
            "payload for analytics and performance treatment."
        ),
    )
    synthetic_flow_effective_date: Optional[date] = Field(
        default=None,
        json_schema_extra={"example": "2026-03-15"},
        description=(
            "Effective business date of the synthetic flow used in corporate-action analytics."
        ),
    )
    synthetic_flow_amount_local: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "-10000.00"},
        description=(
            "Synthetic flow amount in the local flow currency before base currency translation."
        ),
    )
    synthetic_flow_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "USD"},
        description="Currency in which synthetic_flow_amount_local is expressed.",
    )
    synthetic_flow_amount_base: Optional[condecimal()] = Field(
        default=None,
        json_schema_extra={"example": "-10000.00"},
        description=("Synthetic flow amount translated into the portfolio base currency."),
    )
    synthetic_flow_fx_rate_to_base: Optional[condecimal(gt=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "1.000000"},
        description=(
            "FX rate used to derive synthetic_flow_amount_base from the local "
            "synthetic flow amount."
        ),
    )
    synthetic_flow_price_used: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "200.00"},
        description=(
            "Price input used when the synthetic flow valuation method depends "
            "on market-value transfer pricing."
        ),
    )
    synthetic_flow_quantity_used: Optional[condecimal(ge=Decimal(0))] = Field(
        default=None,
        json_schema_extra={"example": "50.00"},
        description=(
            "Quantity input used when the synthetic flow valuation method "
            "depends on market-value transfer quantity."
        ),
    )
    synthetic_flow_valuation_method: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "MVT_PRICE_X_QTY"},
        description=(
            "Synthetic flow valuation method classification used to explain "
            "how the synthetic amount was derived."
        ),
    )
    synthetic_flow_classification: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "POSITION_TRANSFER_OUT"},
        description=(
            "Synthetic flow classification used by position-level analytics "
            "and performance engines."
        ),
    )
    synthetic_flow_price_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM"},
        description=("Source classification for the price input used in synthetic flow valuation."),
    )
    synthetic_flow_fx_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX_SERVICE"},
        description=("Source classification for the FX input used in synthetic flow translation."),
    )
    synthetic_flow_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM_PROVIDED"},
        description=(
            "Origin descriptor that explains whether the synthetic flow was "
            "supplied upstream or derived internally."
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Ingestion-side creation timestamp for lineage and troubleshooting.",
        json_schema_extra={"example": "2026-03-10T11:32:15Z"},
    )


class TransactionIngestionRequest(BaseModel):
    transactions: List[Transaction] = Field(
        ...,
        description=(
            "Canonical transaction records to ingest or upsert asynchronously. "
            "An empty list is accepted as a no-op batch for client workflow consistency."
        ),
        examples=[
            [],
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
            ],
        ],
    )
