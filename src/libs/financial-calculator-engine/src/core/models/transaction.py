# libs/financial-calculator-engine/src/core/models/transaction.py

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, condecimal, field_validator


class Fees(BaseModel):
    """
    Represents various fees associated with a transaction.
    """

    stamp_duty: condecimal(ge=0) = Field(default=Decimal(0), description="Stamp duty fee")
    exchange_fee: condecimal(ge=0) = Field(default=Decimal(0), description="Exchange fee")
    gst: condecimal(ge=0) = Field(default=Decimal(0), description="Goods and Services Tax")
    brokerage: condecimal(ge=0) = Field(default=Decimal(0), description="Brokerage fee")
    other_fees: condecimal(ge=0) = Field(
        default=Decimal(0), description="Any other miscellaneous fees"
    )

    @property
    def total_fees(self) -> Decimal:
        """Calculates the sum of all fees."""
        return self.stamp_duty + self.exchange_fee + self.gst + self.brokerage + self.other_fees


class Transaction(BaseModel):
    """
    Represents a single financial transaction.
    """

    transaction_id: str = Field(..., description="Unique identifier for the transaction")
    portfolio_id: str = Field(..., description="Identifier for the portfolio")
    instrument_id: str = Field(..., description="Identifier for the instrument (e.g., ticker)")
    security_id: str = Field(..., description="Unique identifier for the specific security")
    transaction_type: str = Field(
        ..., description="Type of transaction (e.g., BUY, SELL, DIVIDEND)"
    )
    transaction_date: datetime = Field(
        ..., description="Date the transaction occurred (ISO format)"
    )
    settlement_date: Optional[datetime] = Field(
        None, description="Date the transaction settled (ISO format)"
    )
    quantity: condecimal(ge=0) = Field(..., description="Quantity of the instrument involved")
    gross_transaction_amount: condecimal(ge=0) = Field(
        ..., description="Gross amount of the transaction"
    )
    net_transaction_amount: Optional[condecimal(ge=0)] = Field(
        None, description="Net amount of the transaction"
    )
    fees: Optional[Fees] = Field(default_factory=Fees, description="Detailed breakdown of fees")
    accrued_interest: Optional[condecimal(ge=0)] = Field(
        default=Decimal(0), description="Accrued interest"
    )
    average_price: Optional[condecimal(ge=0)] = Field(
        None, description="Average price of the instrument"
    )
    trade_currency: str = Field(..., description="Currency of the transaction")

    portfolio_base_currency: str = Field(..., description="The base currency of the portfolio")
    transaction_fx_rate: Optional[condecimal(gt=0)] = Field(
        None, description="FX rate used for this transaction (Local to Base)"
    )

    net_cost: Optional[condecimal()] = Field(
        None, description="Calculated net cost for BUYs in portfolio base currency"
    )
    gross_cost: Optional[condecimal()] = Field(
        None, description="Calculated gross cost for BUYs in portfolio base currency"
    )
    realized_gain_loss: Optional[condecimal()] = Field(
        None, description="Calculated realized gain/loss for SELLs in portfolio base currency"
    )

    net_cost_local: Optional[condecimal()] = Field(
        None, description="Calculated net cost for BUYs in instrument's local currency"
    )
    realized_gain_loss_local: Optional[condecimal()] = Field(
        None, description="Calculated realized gain/loss for SELLs in instrument's local currency"
    )

    error_reason: Optional[str] = Field(
        None, description="Reason for transaction processing failure"
    )

    @field_validator("transaction_date", "settlement_date", mode="before")
    @classmethod
    def standardize_datetimes(cls, v: Any) -> Any:
        """Ensure all incoming datetimes are timezone-aware (UTC)."""
        if v is None:
            return v
        if isinstance(v, str):
            if v.endswith("Z"):
                v = v[:-1] + "+00:00"
            v = datetime.fromisoformat(v)

        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=False, extra="allow")
