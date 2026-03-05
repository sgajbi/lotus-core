# services/query-service/app/dtos/transaction_dto.py
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .cashflow_dto import CashflowRecord


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
    transaction_type: str = Field(..., description="Transaction type.", examples=["BUY"])
    instrument_id: str = Field(..., description="Instrument identifier.", examples=["AAPL"])
    security_id: str = Field(..., description="Security identifier.", examples=["US0378331005"])
    quantity: Decimal = Field(..., description="Signed transaction quantity.", examples=[100.0])
    price: Decimal = Field(..., description="Execution price per unit.", examples=[185.42])
    gross_transaction_amount: Decimal = Field(
        ..., description="Gross transaction amount before fees.", examples=[18542.0]
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
            "Cash-leg generation mode. AUTO indicates service-generated cashflow; "
            "EXTERNAL indicates upstream-provided separate cash entry."
        ),
        examples=["AUTO"],
    )
    external_cash_transaction_id: Optional[str] = Field(
        None,
        description="Linked upstream cash transaction id when cash_entry_mode is EXTERNAL.",
        examples=["CASH-ENTRY-2026-0001"],
    )
    cashflow: Optional[CashflowRecord] = Field(
        None, description="Linked cashflow details when available."
    )

    model_config = ConfigDict(from_attributes=True)


class PaginatedTransactionResponse(BaseModel):
    """
    Represents the paginated API response for a transaction query.
    """

    portfolio_id: str = Field(..., description="The ID of the portfolio.")
    total: int = Field(..., description="The total number of transactions matching the query.")
    skip: int = Field(..., description="The number of records skipped (offset).")
    limit: int = Field(..., description="The maximum number of records returned.")
    transactions: List[TransactionRecord] = Field(
        ..., description="The list of transaction records for the current page."
    )
