from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InterestCanonicalTransaction(BaseModel):
    """
    Slice 1 canonical INTEREST contract foundation.
    Focuses on deterministic validation and policy/linkage traceability fields.
    """

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    transaction_id: str = Field(..., description="Unique transaction identifier.")
    transaction_type: str = Field(..., description="Canonical transaction type.")

    portfolio_id: str = Field(..., description="Portfolio receiving or paying interest.")
    instrument_id: str = Field(..., description="Instrument identifier.")
    security_id: str = Field(..., description="Security identifier.")

    transaction_date: datetime = Field(..., description="Interest booking timestamp.")
    settlement_date: Optional[datetime] = Field(
        default=None, description="Contractual settlement timestamp."
    )

    quantity: Decimal = Field(
        ..., description="Quantity impact. Canonical INTEREST requires zero."
    )
    price: Decimal = Field(
        ..., description="Unit price impact. Canonical INTEREST requires zero."
    )
    gross_transaction_amount: Decimal = Field(
        ..., description="Gross interest amount in trade currency."
    )
    trade_fee: Optional[Decimal] = Field(
        default=Decimal(0), description="Transaction fee amount if applicable."
    )

    trade_currency: str = Field(..., description="Trade/settlement currency.")
    currency: str = Field(..., description="Booked transaction currency.")

    economic_event_id: Optional[str] = Field(
        default=None,
        description="Shared economic event identifier used for interest/cash linkage.",
    )
    linked_transaction_group_id: Optional[str] = Field(
        default=None, description="Group identifier for linked transactional entries."
    )

    calculation_policy_id: Optional[str] = Field(
        default=None, description="Resolved policy identifier."
    )
    calculation_policy_version: Optional[str] = Field(
        default=None, description="Resolved policy version."
    )
    cash_entry_mode: Optional[str] = Field(
        default=None,
        description=(
            "Cash-leg generation mode. AUTO for service-generated cash leg, "
            "EXTERNAL for upstream-provided cash entry."
        ),
    )
    external_cash_transaction_id: Optional[str] = Field(
        default=None,
        description="Upstream cash transaction identifier when cash_entry_mode is EXTERNAL.",
    )
