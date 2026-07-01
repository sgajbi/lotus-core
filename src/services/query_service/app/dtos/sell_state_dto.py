from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class SellDisposalRecord(BaseModel):
    transaction_id: str = Field(
        ..., description="SELL transaction identifier.", examples=["TXN-SELL-2026-0001"]
    )
    transaction_date: datetime = Field(
        ...,
        description="SELL transaction event timestamp used for disposal chronology.",
        examples=["2026-03-01T09:30:00Z"],
    )
    instrument_id: str = Field(..., description="Instrument identifier.", examples=["AAPL"])
    security_id: str = Field(..., description="Security identifier.", examples=["US0378331005"])
    quantity_disposed: Decimal = Field(
        ..., description="Absolute quantity disposed by this SELL.", examples=[25.0]
    )
    disposal_cost_basis_base: Optional[Decimal] = Field(
        None,
        description="Disposed cost basis in portfolio base currency (absolute value).",
        examples=[3750.0],
    )
    disposal_cost_basis_local: Optional[Decimal] = Field(
        None,
        description="Disposed cost basis in trade/local currency (absolute value).",
        examples=[3750.0],
    )
    net_sell_proceeds_base: Optional[Decimal] = Field(
        None,
        description="Net SELL proceeds in portfolio base currency after fees.",
        examples=[4250.0],
    )
    net_sell_proceeds_local: Optional[Decimal] = Field(
        None,
        description="Net SELL proceeds in trade/local currency after fees.",
        examples=[4250.0],
    )
    realized_gain_loss_base: Optional[Decimal] = Field(
        None,
        description="Realized gain/loss in portfolio base currency for this SELL.",
        examples=[500.0],
    )
    realized_gain_loss_local: Optional[Decimal] = Field(
        None,
        description="Realized gain/loss in trade/local currency for this SELL.",
        examples=[500.0],
    )
    economic_event_id: Optional[str] = Field(
        None,
        description="Economic event identifier linking security and cash effects.",
        examples=["EVT-SELL-PORT-10001-TXN-SELL-2026-0001"],
    )
    linked_transaction_group_id: Optional[str] = Field(
        None,
        description="Linked transaction group identifier for reconciliation.",
        examples=["LTG-SELL-PORT-10001-TXN-SELL-2026-0001"],
    )
    calculation_policy_id: Optional[str] = Field(
        None,
        description="Calculation policy identifier used for SELL disposal.",
        examples=["SELL_FIFO_POLICY"],
    )
    calculation_policy_version: Optional[str] = Field(
        None,
        description="Calculation policy version used for SELL disposal.",
        examples=["1.0.0"],
    )
    source_system: Optional[str] = Field(
        None,
        description="Upstream source system that originated the transaction.",
        examples=["OMS_PRIMARY"],
    )


class SellDisposalsResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-10001"])
    security_id: str = Field(
        ..., description="Security identifier used for filtering.", examples=["US0378331005"]
    )
    sell_disposals: List[SellDisposalRecord] = Field(
        ..., description="SELL disposal records in descending transaction date order."
    )


class SellCashLinkageResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-10001"])
    transaction_id: str = Field(
        ..., description="SELL transaction identifier.", examples=["TXN-SELL-2026-0001"]
    )
    transaction_type: str = Field(..., description="Transaction type.", examples=["SELL"])
    economic_event_id: Optional[str] = Field(
        None,
        description="Economic event identifier used for reconciliation.",
        examples=["EVT-SELL-PORT-10001-TXN-SELL-2026-0001"],
    )
    linked_transaction_group_id: Optional[str] = Field(
        None,
        description="Group identifier linking security and cash effects.",
        examples=["LTG-SELL-PORT-10001-TXN-SELL-2026-0001"],
    )
    calculation_policy_id: Optional[str] = Field(
        None,
        description="Calculation policy identifier used for SELL disposal.",
        examples=["SELL_FIFO_POLICY"],
    )
    calculation_policy_version: Optional[str] = Field(
        None,
        description="Calculation policy version used for SELL disposal.",
        examples=["1.0.0"],
    )
    cashflow_date: Optional[datetime] = Field(
        None,
        description="Linked settlement cashflow booking date.",
        examples=["2026-03-03T00:00:00Z"],
    )
    cashflow_amount: Optional[Decimal] = Field(
        None,
        description="Linked settlement cashflow amount.",
        examples=[4250.0],
    )
    cashflow_currency: Optional[str] = Field(
        None, description="Currency of linked cashflow.", examples=["USD"]
    )
    cashflow_classification: Optional[str] = Field(
        None,
        description="Cashflow classification for the linked settlement event.",
        examples=["INVESTMENT_INFLOW"],
    )
