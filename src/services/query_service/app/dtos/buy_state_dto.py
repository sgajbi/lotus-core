from decimal import Decimal
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PositionLotRecord(BaseModel):
    lot_id: str = Field(..., description="Stable lot identifier.", examples=["LOT-TXN-2026-0001"])
    source_transaction_id: str = Field(
        ..., description="Transaction ID that created this lot.", examples=["TXN-2026-0001"]
    )
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-10001"])
    instrument_id: str = Field(..., description="Instrument identifier.", examples=["AAPL"])
    security_id: str = Field(..., description="Security identifier.", examples=["US0378331005"])
    acquisition_date: date = Field(..., description="Lot acquisition date.", examples=["2026-02-28"])
    original_quantity: float = Field(..., description="Original acquired quantity.", examples=[100.0])
    open_quantity: float = Field(..., description="Current open quantity.", examples=[100.0])
    lot_cost_local: Decimal = Field(..., description="Lot cost in trade/local currency.", examples=[15005.5])
    lot_cost_base: Decimal = Field(..., description="Lot cost in base currency.", examples=[15005.5])
    accrued_interest_paid_local: Decimal = Field(
        ..., description="Accrued interest paid on acquisition in local currency.", examples=[1250.0]
    )
    economic_event_id: Optional[str] = Field(
        None, description="Economic event identifier linking security/cash effects.", examples=["EVT-2026-00987"]
    )
    linked_transaction_group_id: Optional[str] = Field(
        None, description="Group ID linking related transactions.", examples=["LTG-2026-00456"]
    )
    calculation_policy_id: Optional[str] = Field(
        None, description="Calculation policy identifier used for BUY processing.", examples=["BUY_DEFAULT_POLICY"]
    )
    calculation_policy_version: Optional[str] = Field(
        None, description="Version of calculation policy used.", examples=["1.0.0"]
    )
    source_system: Optional[str] = Field(
        None, description="Source system from which this transaction originated.", examples=["OMS_PRIMARY"]
    )

    model_config = ConfigDict(from_attributes=True)


class PositionLotsResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-10001"])
    security_id: str = Field(..., description="Security identifier.", examples=["US0378331005"])
    lots: List[PositionLotRecord] = Field(
        ..., description="Current lot records for the portfolio-security key."
    )


class AccruedIncomeOffsetRecord(BaseModel):
    offset_id: str = Field(..., description="Stable accrued-income offset identifier.", examples=["AIO-TXN-2026-0001"])
    source_transaction_id: str = Field(
        ..., description="Transaction ID that initialized this offset.", examples=["TXN-2026-0001"]
    )
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-10001"])
    instrument_id: str = Field(..., description="Instrument identifier.", examples=["AAPL"])
    security_id: str = Field(..., description="Security identifier.", examples=["US0378331005"])
    accrued_interest_paid_local: Decimal = Field(
        ..., description="Accrued interest paid at BUY booking in local currency.", examples=[1250.0]
    )
    remaining_offset_local: Decimal = Field(
        ..., description="Remaining accrued-income offset available for net-income calculations.", examples=[1250.0]
    )
    economic_event_id: Optional[str] = Field(
        None, description="Economic event identifier linking security/cash effects.", examples=["EVT-2026-00987"]
    )
    linked_transaction_group_id: Optional[str] = Field(
        None, description="Group ID linking related transactions.", examples=["LTG-2026-00456"]
    )
    calculation_policy_id: Optional[str] = Field(
        None, description="Calculation policy identifier used for BUY processing.", examples=["BUY_DEFAULT_POLICY"]
    )
    calculation_policy_version: Optional[str] = Field(
        None, description="Version of calculation policy used.", examples=["1.0.0"]
    )
    source_system: Optional[str] = Field(
        None, description="Source system from which this transaction originated.", examples=["OMS_PRIMARY"]
    )

    model_config = ConfigDict(from_attributes=True)


class AccruedIncomeOffsetsResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-10001"])
    security_id: str = Field(..., description="Security identifier.", examples=["US0378331005"])
    offsets: List[AccruedIncomeOffsetRecord] = Field(
        ..., description="Accrued-income offset records for the portfolio-security key."
    )


class BuyCashLinkageResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-10001"])
    transaction_id: str = Field(
        ..., description="Security-side BUY transaction identifier.", examples=["TXN-2026-0001"]
    )
    transaction_type: str = Field(..., description="Transaction type.", examples=["BUY"])
    economic_event_id: Optional[str] = Field(
        None, description="Economic event identifier used for reconciliation.", examples=["EVT-2026-00987"]
    )
    linked_transaction_group_id: Optional[str] = Field(
        None, description="Group ID used to link cash and security effects.", examples=["LTG-2026-00456"]
    )
    calculation_policy_id: Optional[str] = Field(
        None,
        description="Calculation policy identifier used for BUY processing.",
        examples=["BUY_DEFAULT_POLICY"],
    )
    calculation_policy_version: Optional[str] = Field(
        None,
        description="Version of calculation policy used.",
        examples=["1.0.0"],
    )
    cashflow_date: Optional[datetime] = Field(
        None, description="Linked cashflow booking date.", examples=["2026-02-28T00:00:00Z"]
    )
    cashflow_amount: Optional[Decimal] = Field(
        None, description="Linked cashflow amount.", examples=[-15005.5]
    )
    cashflow_currency: Optional[str] = Field(
        None, description="Currency of linked cashflow.", examples=["USD"]
    )
    cashflow_classification: Optional[str] = Field(
        None, description="Cashflow classification.", examples=["INVESTMENT_OUTFLOW"]
    )
