from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

FX_BUSINESS_TRANSACTION_TYPES = {"FX_SPOT", "FX_FORWARD", "FX_SWAP"}
FX_COMPONENT_TYPES = {
    "FX_CONTRACT_OPEN",
    "FX_CONTRACT_CLOSE",
    "FX_CASH_SETTLEMENT_BUY",
    "FX_CASH_SETTLEMENT_SELL",
}
FX_CASH_LEG_ROLES = {"BUY", "SELL"}
FX_RATE_QUOTE_CONVENTIONS = {"QUOTE_PER_BASE", "BASE_PER_QUOTE"}
FX_SPOT_EXPOSURE_MODELS = {"NONE", "FX_CONTRACT"}
FX_REALIZED_PNL_MODES = {"NONE", "UPSTREAM_PROVIDED", "CASH_LOT_COST_METHOD"}


class FxCanonicalTransaction(BaseModel):
    """
    Slice 1 canonical FX contract foundation.
    Models one persisted FX component row with the metadata required to keep
    business type, component semantics, and linkage explicit.
    """

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    transaction_id: str = Field(..., description="Unique transaction identifier.")
    transaction_type: str = Field(
        ..., description="Canonical FX business transaction type."
    )
    component_type: str = Field(..., description="Canonical FX component type.")
    component_id: str = Field(..., description="Unique component identifier within the FX group.")
    linked_component_ids: Optional[list[str]] = Field(
        default=None,
        description="Other FX component identifiers linked to this component.",
    )

    portfolio_id: str = Field(..., description="Portfolio identifier.")
    instrument_id: str = Field(..., description="Instrument identifier.")
    security_id: str = Field(..., description="Security identifier.")

    transaction_date: datetime = Field(..., description="Trade or booking timestamp.")
    settlement_date: Optional[datetime] = Field(
        default=None,
        description="Settlement or maturity timestamp for this FX component.",
    )

    quantity: Decimal = Field(
        ..., description="Canonical FX foundation requires quantity to remain zero."
    )
    price: Decimal = Field(
        ..., description="Canonical FX foundation requires price to remain zero."
    )
    gross_transaction_amount: Decimal = Field(
        ..., description="Gross transaction amount for the persisted FX component row."
    )

    trade_currency: str = Field(..., description="Trade currency code.")
    currency: str = Field(..., description="Book currency code.")
    pair_base_currency: str = Field(..., description="Currency pair base currency.")
    pair_quote_currency: str = Field(..., description="Currency pair quote currency.")
    fx_rate_quote_convention: str = Field(
        ..., description="Explicit FX rate quote convention."
    )

    buy_currency: str = Field(..., description="Currency received at settlement.")
    sell_currency: str = Field(..., description="Currency delivered at settlement.")
    buy_amount: Decimal = Field(..., description="Positive magnitude of bought currency.")
    sell_amount: Decimal = Field(..., description="Positive magnitude of sold currency.")
    contract_rate: Decimal = Field(..., description="Contractual FX rate.")

    economic_event_id: Optional[str] = Field(
        default=None, description="Economic event id shared by all FX components."
    )
    linked_transaction_group_id: Optional[str] = Field(
        default=None, description="Linked group id shared by related FX components."
    )
    calculation_policy_id: Optional[str] = Field(
        default=None, description="Resolved policy identifier."
    )
    calculation_policy_version: Optional[str] = Field(
        default=None, description="Resolved policy version."
    )

    fx_cash_leg_role: Optional[str] = Field(
        default=None, description="BUY or SELL role for settlement cash components."
    )
    linked_fx_cash_leg_id: Optional[str] = Field(
        default=None, description="Opposite FX cash-leg transaction identifier."
    )
    settlement_status: Optional[str] = Field(
        default=None, description="Settlement status for FX cash components."
    )

    fx_contract_id: Optional[str] = Field(
        default=None, description="Stable FX contract identifier."
    )
    fx_contract_open_transaction_id: Optional[str] = Field(
        default=None, description="Linked contract-open transaction identifier."
    )
    fx_contract_close_transaction_id: Optional[str] = Field(
        default=None, description="Linked contract-close transaction identifier."
    )
    settlement_of_fx_contract_id: Optional[str] = Field(
        default=None,
        description="FX contract identifier that the settlement component closes or settles.",
    )

    swap_event_id: Optional[str] = Field(default=None, description="Stable FX swap identifier.")
    near_leg_group_id: Optional[str] = Field(
        default=None, description="Near-leg group id for FX swaps."
    )
    far_leg_group_id: Optional[str] = Field(
        default=None, description="Far-leg group id for FX swaps."
    )

    spot_exposure_model: Optional[str] = Field(
        default=None, description="Policy-driven spot exposure model."
    )
    fx_realized_pnl_mode: Optional[str] = Field(
        default=None, description="Policy-driven realized FX P&L mode."
    )
    realized_capital_pnl_local: Optional[Decimal] = Field(
        default=None, description="Realized capital P&L in local currency. Must be zero for FX."
    )
    realized_fx_pnl_local: Optional[Decimal] = Field(
        default=None, description="Realized FX P&L in local currency."
    )
    realized_total_pnl_local: Optional[Decimal] = Field(
        default=None, description="Total realized P&L in local currency."
    )
    realized_capital_pnl_base: Optional[Decimal] = Field(
        default=None, description="Realized capital P&L in base currency. Must be zero for FX."
    )
    realized_fx_pnl_base: Optional[Decimal] = Field(
        default=None, description="Realized FX P&L in base currency."
    )
    realized_total_pnl_base: Optional[Decimal] = Field(
        default=None, description="Total realized P&L in base currency."
    )
