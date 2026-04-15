# services/query-service/app/dtos/transaction_dto.py
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .cashflow_dto import CashflowRecord
from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


class TransactionCostRecord(BaseModel):
    fee_type: str = Field(..., description="Fee type or cost category.", examples=["BROKERAGE"])
    amount: Decimal = Field(
        ...,
        description="Monetary amount of the transaction cost in the stated fee currency.",
        examples=[12.5],
    )
    currency: str = Field(..., description="Fee currency.", examples=["USD"])

    model_config = ConfigDict(from_attributes=True)


class TransactionRecord(BaseModel):
    """
    Represents a single, detailed transaction record for API responses.
    """

    transaction_id: str = Field(
        ..., description="Transaction identifier.", examples=["TXN-2026-0001"]
    )
    transaction_date: datetime = Field(
        ..., description="Transaction booking timestamp.", examples=["2026-03-01T09:30:00Z"]
    )
    settlement_date: Optional[datetime] = Field(
        None,
        description=(
            "Canonical settlement timestamp when known. Use alongside transaction_date to "
            "differentiate trade booking from contractual or effective cash/value settlement."
        ),
        examples=["2026-03-03T00:00:00Z"],
    )
    transaction_type: str = Field(..., description="Transaction type.", examples=["BUY"])
    instrument_id: str = Field(..., description="Instrument identifier.", examples=["AAPL"])
    security_id: str = Field(..., description="Security identifier.", examples=["US0378331005"])
    quantity: Decimal = Field(..., description="Signed transaction quantity.", examples=[100.0])
    price: Decimal = Field(..., description="Execution price per unit.", examples=[185.42])
    gross_transaction_amount: Decimal = Field(
        ..., description="Gross transaction amount before fees.", examples=[18542.0]
    )
    gross_cost: Optional[Decimal] = Field(
        None,
        description="Gross cost impact before fees and adjustments.",
        examples=[18542.0],
    )
    trade_fee: Optional[Decimal] = Field(
        None,
        description="Primary trade fee recorded directly on the transaction.",
        examples=[12.5],
    )
    trade_currency: Optional[str] = Field(
        None,
        description="Trade or execution currency when distinct from book currency.",
        examples=["USD"],
    )
    currency: str = Field(..., description="Book currency code.", examples=["USD"])

    net_cost: Optional[Decimal] = Field(
        None,
        description="Net cost impact in base currency. SELL disposal values are negative.",
        examples=[-3750.0],
    )
    realized_gain_loss: Optional[Decimal] = Field(
        None, description="Realized gain/loss in base currency.", examples=[500.0]
    )

    net_cost_local: Optional[Decimal] = Field(
        None,
        description="Net cost impact in local/trade currency. SELL disposal values are negative.",
        examples=[-3750.0],
    )
    realized_gain_loss_local: Optional[Decimal] = Field(
        None, description="Realized gain/loss in local/trade currency.", examples=[500.0]
    )

    transaction_fx_rate: Optional[Decimal] = Field(
        None,
        description="FX rate from local/trade currency to portfolio base currency.",
        examples=[1.08],
    )
    economic_event_id: Optional[str] = Field(
        None,
        description="Economic event identifier linking security and cash effects.",
        examples=["EVT-SELL-PORT-10001-TXN-SELL-2026-0001"],
    )
    linked_transaction_group_id: Optional[str] = Field(
        None,
        description="Group identifier linking related transactions for reconciliation.",
        examples=["LTG-SELL-PORT-10001-TXN-SELL-2026-0001"],
    )
    calculation_policy_id: Optional[str] = Field(
        None,
        description="Calculation policy identifier used by processing engines.",
        examples=["SELL_FIFO_POLICY"],
    )
    calculation_policy_version: Optional[str] = Field(
        None, description="Version of the calculation policy.", examples=["1.0.0"]
    )
    source_system: Optional[str] = Field(
        None, description="Upstream source system identifier.", examples=["OMS_PRIMARY"]
    )
    cash_entry_mode: Optional[str] = Field(
        None,
        description=(
            "Cash-leg generation mode. AUTO_GENERATE indicates service-generated "
            "cashflow; UPSTREAM_PROVIDED indicates upstream-provided separate cash "
            "entry."
        ),
        examples=["AUTO_GENERATE"],
    )
    external_cash_transaction_id: Optional[str] = Field(
        None,
        description=(
            "Linked upstream cash transaction id when cash_entry_mode is UPSTREAM_PROVIDED."
        ),
        examples=["CASH-ENTRY-2026-0001"],
    )
    settlement_cash_account_id: Optional[str] = Field(
        None,
        description=(
            "Settlement cash account identifier used for generated ADJUSTMENT cash "
            "leg construction in AUTO_GENERATE mode."
        ),
        examples=["CASH-ACC-USD-001"],
    )
    settlement_cash_instrument_id: Optional[str] = Field(
        None,
        description=("Cash instrument identifier used for generated ADJUSTMENT cash legs."),
        examples=["CASH-USD"],
    )
    movement_direction: Optional[str] = Field(
        None,
        description="Cash movement direction for ADJUSTMENT transactions (INFLOW or OUTFLOW).",
        examples=["INFLOW"],
    )
    originating_transaction_id: Optional[str] = Field(
        None,
        description="Originating product-leg transaction id linked to an ADJUSTMENT cash leg.",
        examples=["TRN001"],
    )
    originating_transaction_type: Optional[str] = Field(
        None,
        description="Originating product-leg transaction type linked to an ADJUSTMENT cash leg.",
        examples=["BUY"],
    )
    adjustment_reason: Optional[str] = Field(
        None,
        description="Canonical reason code describing why an ADJUSTMENT cash leg exists.",
        examples=["BUY_SETTLEMENT"],
    )
    link_type: Optional[str] = Field(
        None,
        description="Canonical relationship label between product leg and ADJUSTMENT cash leg.",
        examples=["BUY_TO_CASH"],
    )
    reconciliation_key: Optional[str] = Field(
        None,
        description="Optional reconciliation key shared by paired dual-leg transactions.",
        examples=["REC-2026-0001"],
    )
    interest_direction: Optional[str] = Field(
        None,
        description="INTEREST semantic direction when applicable.",
        examples=["INCOME"],
    )
    withholding_tax_amount: Optional[Decimal] = Field(
        None,
        description="Withholding tax amount captured for INTEREST transactions.",
        examples=[15.25],
    )
    other_interest_deductions_amount: Optional[Decimal] = Field(
        None,
        description="Other deductions captured for INTEREST transactions.",
        examples=[1.0],
    )
    net_interest_amount: Optional[Decimal] = Field(
        None,
        description="Net-interest amount when provided for reconciliation.",
        examples=[108.2],
    )
    component_type: Optional[str] = Field(
        None,
        description="Canonical FX component type when transaction_type is an FX business type.",
        examples=["FX_CASH_SETTLEMENT_BUY"],
    )
    component_id: Optional[str] = Field(
        None,
        description="Unique FX component identifier within the linked transaction group.",
        examples=["FX-COMP-0001"],
    )
    linked_component_ids: Optional[List[str]] = Field(
        None,
        description="Related FX component identifiers within the same economic event.",
        examples=[["FX-COMP-0002", "FX-COMP-0003"]],
    )
    fx_cash_leg_role: Optional[str] = Field(
        None, description="FX cash-leg role when applicable.", examples=["BUY"]
    )
    linked_fx_cash_leg_id: Optional[str] = Field(
        None,
        description="Opposite FX cash settlement transaction identifier.",
        examples=["FX-SETTLE-SELL-0001"],
    )
    settlement_status: Optional[str] = Field(
        None,
        description="Settlement status for FX cash settlement components.",
        examples=["PENDING"],
    )
    pair_base_currency: Optional[str] = Field(
        None, description="Base currency of the quoted FX pair.", examples=["EUR"]
    )
    pair_quote_currency: Optional[str] = Field(
        None, description="Quote currency of the quoted FX pair.", examples=["USD"]
    )
    fx_rate_quote_convention: Optional[str] = Field(
        None,
        description="Explicit FX quote convention.",
        examples=["QUOTE_PER_BASE"],
    )
    buy_currency: Optional[str] = Field(
        None, description="Currency bought/received by the FX transaction.", examples=["USD"]
    )
    sell_currency: Optional[str] = Field(
        None, description="Currency sold/delivered by the FX transaction.", examples=["EUR"]
    )
    buy_amount: Optional[Decimal] = Field(
        None, description="Positive magnitude of currency bought.", examples=[1095000.0]
    )
    sell_amount: Optional[Decimal] = Field(
        None, description="Positive magnitude of currency sold.", examples=[1000000.0]
    )
    contract_rate: Optional[Decimal] = Field(
        None, description="Contractual FX rate.", examples=[1.095]
    )
    fx_contract_id: Optional[str] = Field(
        None, description="Stable FX contract identifier.", examples=["FXC-2026-0001"]
    )
    fx_contract_open_transaction_id: Optional[str] = Field(
        None,
        description="Linked FX contract-open transaction identifier.",
        examples=["FX-OPEN-0001"],
    )
    fx_contract_close_transaction_id: Optional[str] = Field(
        None,
        description="Linked FX contract-close transaction identifier.",
        examples=["FX-CLOSE-0001"],
    )
    settlement_of_fx_contract_id: Optional[str] = Field(
        None,
        description="FX contract identifier settled by this cash component.",
        examples=["FXC-2026-0001"],
    )
    swap_event_id: Optional[str] = Field(
        None, description="Stable FX swap event identifier.", examples=["FXSWAP-2026-0001"]
    )
    near_leg_group_id: Optional[str] = Field(
        None,
        description="Near-leg group identifier for FX swaps.",
        examples=["FXSWAP-2026-0001-NEAR"],
    )
    far_leg_group_id: Optional[str] = Field(
        None,
        description="Far-leg group identifier for FX swaps.",
        examples=["FXSWAP-2026-0001-FAR"],
    )
    spot_exposure_model: Optional[str] = Field(
        None, description="Policy-driven spot exposure model.", examples=["NONE"]
    )
    fx_realized_pnl_mode: Optional[str] = Field(
        None, description="Policy-driven realized FX P&L mode.", examples=["UPSTREAM_PROVIDED"]
    )
    realized_capital_pnl_local: Optional[Decimal] = Field(
        None,
        description="Realized capital P&L in local currency. Must be zero for FX.",
        examples=[0.0],
    )
    realized_fx_pnl_local: Optional[Decimal] = Field(
        None, description="Realized FX P&L in local currency.", examples=[1250.0]
    )
    realized_total_pnl_local: Optional[Decimal] = Field(
        None, description="Total realized P&L in local currency.", examples=[1250.0]
    )
    realized_capital_pnl_base: Optional[Decimal] = Field(
        None,
        description="Realized capital P&L in base currency. Must be zero for FX.",
        examples=[0.0],
    )
    realized_fx_pnl_base: Optional[Decimal] = Field(
        None, description="Realized FX P&L in base currency.", examples=[1250.0]
    )
    realized_total_pnl_base: Optional[Decimal] = Field(
        None, description="Total realized P&L in base currency.", examples=[1250.0]
    )
    parent_transaction_reference: Optional[str] = Field(
        None,
        description="Corporate-action parent transaction reference for child linkage.",
        examples=["CA_PARENT_TXN_001"],
    )
    linked_parent_event_id: Optional[str] = Field(
        None,
        description="Linked corporate-action parent event identifier.",
        examples=["CA-EVT-2026-0001"],
    )
    parent_event_reference: Optional[str] = Field(
        None,
        description="Upstream parent-event reference shared by related CA children.",
        examples=["UPSTREAM-CA-REF-2026-0001"],
    )
    child_role: Optional[str] = Field(
        None,
        description="Canonical corporate-action child role.",
        examples=["SOURCE_POSITION_CLOSE"],
    )
    child_sequence_hint: Optional[int] = Field(
        None,
        description="Optional upstream child sequence hint.",
        examples=[10],
    )
    dependency_reference_ids: Optional[List[str]] = Field(
        None,
        description="Optional dependency references for CA child ordering.",
        examples=[["CA-CHILD-OUT-001"]],
    )
    source_instrument_id: Optional[str] = Field(
        None,
        description="Source instrument identifier for transfer-style corporate actions.",
        examples=["OLD_SEC_001"],
    )
    target_instrument_id: Optional[str] = Field(
        None,
        description="Target instrument identifier for transfer-style corporate actions.",
        examples=["NEW_SEC_001"],
    )
    source_transaction_reference: Optional[str] = Field(
        None,
        description="Reference to source-side corporate-action child transaction.",
        examples=["CA-CHILD-OUT-001"],
    )
    target_transaction_reference: Optional[str] = Field(
        None,
        description="Reference to target-side corporate-action child transaction.",
        examples=["CA-CHILD-IN-001"],
    )
    linked_cash_transaction_id: Optional[str] = Field(
        None,
        description="Linked cash transaction id for CASH_IN_LIEU settlement.",
        examples=["CA-CIL-CASH-001"],
    )
    has_synthetic_flow: Optional[bool] = Field(
        None,
        description="Whether this transaction carries position-level synthetic flow details.",
        examples=[True],
    )
    synthetic_flow_effective_date: Optional[date] = Field(
        None,
        description="Synthetic flow effective date used by CA analytics.",
        examples=["2026-03-15"],
    )
    synthetic_flow_amount_local: Optional[Decimal] = Field(
        None,
        description="Synthetic flow amount in local flow currency.",
        examples=[-10000.0],
    )
    synthetic_flow_currency: Optional[str] = Field(
        None,
        description="Currency of synthetic flow amount.",
        examples=["USD"],
    )
    synthetic_flow_amount_base: Optional[Decimal] = Field(
        None,
        description="Synthetic flow amount translated to portfolio base currency.",
        examples=[-10000.0],
    )
    synthetic_flow_fx_rate_to_base: Optional[Decimal] = Field(
        None,
        description="FX rate used to translate synthetic flow local amount to base.",
        examples=[1.0],
    )
    synthetic_flow_price_used: Optional[Decimal] = Field(
        None,
        description="Price input used for synthetic MVT valuation.",
        examples=[200.0],
    )
    synthetic_flow_quantity_used: Optional[Decimal] = Field(
        None,
        description="Quantity input used for synthetic MVT valuation.",
        examples=[50.0],
    )
    synthetic_flow_valuation_method: Optional[str] = Field(
        None,
        description="Synthetic flow valuation method.",
        examples=["MVT_PRICE_X_QTY"],
    )
    synthetic_flow_classification: Optional[str] = Field(
        None,
        description="Synthetic flow classification for position-level analytics.",
        examples=["POSITION_TRANSFER_OUT"],
    )
    synthetic_flow_price_source: Optional[str] = Field(
        None,
        description="Synthetic flow price source.",
        examples=["UPSTREAM"],
    )
    synthetic_flow_fx_source: Optional[str] = Field(
        None,
        description="Synthetic flow FX source.",
        examples=["FX_SERVICE"],
    )
    synthetic_flow_source: Optional[str] = Field(
        None,
        description="Synthetic flow origin descriptor for audit and lineage.",
        examples=["UPSTREAM_PROVIDED"],
    )
    costs: list[TransactionCostRecord] = Field(
        default_factory=list,
        description="Detailed transaction costs associated with the transaction.",
    )
    cashflow: Optional[CashflowRecord] = Field(
        None, description="Linked cashflow details when available."
    )

    model_config = ConfigDict(from_attributes=True)


class PaginatedTransactionResponse(SourceDataProductRuntimeMetadata):
    """
    Represents the paginated API response for a transaction query.
    """

    product_name: Literal["TransactionLedgerWindow"] = product_name_field("TransactionLedgerWindow")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="The ID of the portfolio.")
    total: int = Field(..., description="The total number of transactions matching the query.")
    skip: int = Field(..., description="The number of records skipped (offset).")
    limit: int = Field(..., description="The maximum number of records returned.")
    transactions: List[TransactionRecord] = Field(
        ..., description="The list of transaction records for the current page."
    )
